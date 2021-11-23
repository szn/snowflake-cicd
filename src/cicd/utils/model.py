import shutil
import os
import re
from pathlib import Path

from .log import logger, is_debug
from .dwhrepo import repo
from .snowflake import sf
from .release import release
from .sql import print_sql, sql_meta, get_diff_sql, statement_cleanup
from .utils import get_file_contents
from .config import config


class Model():
    """Handles model .sql definitions."""

    MODEL_DIR    = config.read_config('model_dir', default='model')
    EXTENSIONS   = re.compile(r'.*(\.sql)|(\.vw)|(\.tbl)$', re.I)
    DIFF_DIR     = ".diff"

    def __init__(self):
        self.sf_safe_branch  = repo.get_sf_safe_branch()

    def prepare_release_candidate(self, force):
        """Prepares a release candidate file (if missing)."""
        repo.assert_repo()
        commit_hash = release.get_base_commit(self.sf_safe_branch)
        release.check_release_dir_clean(base_commit=commit_hash)

        files = repo.get_changed_files(index=commit_hash,
                prefix=Model.MODEL_DIR)

        if len(files) == 0:
            logger.info(f"No changes in {Model.MODEL_DIR} dir to prepare release candidate "
                    "file. Preparing empty file.")

        if force:
            logger.info("Not checking if release candidate file was changed due to --force.")
        else:
            release.check_release_candidate()

        branch = repo.get_branch()

        release_candidate_sql = f"--.Release candidate file, branch: {branch}\n\n"
        for change in files.values():
            release_candidate_sql += Model._change_into_release_entry(change, commit_hash)

        release.save_release_candidate_file(release_candidate_sql, branch)
        logger.debug("Release candidate file contents:\n" + release_candidate_sql)

    def deploy_release(self, dry_run=True):
        release_sql = release.prepare_release_file()
        deploy_sql = release.release_file_to_sql(release_sql)

        if is_debug():
            print_sql(deploy_sql)
        if dry_run:
            if not is_debug():
                print_sql(deploy_sql)
            logger.info("Skipping SQL execution due to --dry-run.")
            return

        sf.perform_release(deploy_sql, self.sf_safe_branch)
        release.save_release(release_sql)

        pass
        
    def clone_production(self, force):
        """Clones production database into new db named after branch name."""
        sf.clone_production(self.sf_safe_branch, force)

    def compare_sf_git(self, branch=None):
        """Compares Snowflake and current branch DDLs."""

        if branch is None:
            branch = self.sf_safe_branch

        git_ddls = self.get_all_ddls()
        sf_ddls = sf.get_all_objects(branch)

        logger.info("| {:_^39.39} | {:_^11.11} | {:_^30.30} | {:_^16.16} |".format(
           'object name', 'type', 'GIT file name', 'last change on SF'))   

        for name in sorted(git_ddls.keys() | sf_ddls.keys()):
            o_name = git_ddls.get(name, sf_ddls.get(name))[0]
            o_type = git_ddls.get(name, sf_ddls.get(name))[1]
            o_file = git_ddls.get(name, (None, None, '! MISSING !'))[2][-30:]
            o_date = sf_ddls.get(name, (None, None, None))[2]
            o_date = f"{o_date:%Y-%m-%d %H:%M}" if o_date else '! MISSING !'

            logger.info(f"| {o_name:<39.39} | {o_type:<11.11} | {o_file:^30.30} | {o_date:^16.16} |")
    
    def compare_single_file(self, filename, branch=None):
        if branch is None:
            branch = self.sf_safe_branch
        if not self.EXTENSIONS.search(filename):
            logger.info(f"{filename} is not a SQL file. Running global comparison.")
            self.compare_sf_git(branch=branch)
            return
        
        o_name, o_type, easy_ddl, git_ddl = sql_meta(filename)
        sf_ddl = sf.get_ddl(branch, o_type, o_name)

        if not os.path.exists(self.DIFF_DIR):
            os.makedirs(self.DIFF_DIR)
        sf_filename = os.path.join(self.DIFF_DIR, os.path.basename(filename))
        with open(sf_filename, 'w') as sf_file:
            sf_file.write("-- Snowflake definition --\n")
            sf_file.write(statement_cleanup(sf_ddl))

        print_sql(git_ddl)
        print_sql(sf_ddl)


    def get_all_ddls(self):
        ddls = {}
        for f in Path(self.MODEL_DIR).rglob('*'):
            if self.EXTENSIONS.search(str(f)):
                o_name, o_type, easy_ddl, sql = sql_meta(str(f))
                ddls[(o_type + '#' + o_name).upper()] = (o_name, o_type, str(f))
        return ddls

    @staticmethod
    def _change_into_release_entry(change, commit_hash):
        """Converts a git.change of a file into a release candidate entry (string)."""
        change_type = change.change_type
        filename = change.a_path if change_type == 'D' else change.b_path
        if change_type != 'D':
            o_name, o_type, easy_ddl, sql = sql_meta(filename)

        if change_type == 'D':
            # dropped file/object
            return (f"--.File was removed and *will not* be included in the release.\n"
                    f"-- [{change_type}] NOT_INCLUDED:{filename}\n\n"
                    f"   You have to include a DROP statement to properly sync database state:\n"
                    f"   {release.HERE_STMT}\n\n")
        elif change_type == 'R':
            if easy_ddl:
                return (f"--.File with {o_type} definition was renamed and will be included in the release.\n"
                        f"-- [{change_type}] INCLUDED:{filename}\n\n"
                        f"   If you renamed the object, remember to drop the old one:\n"
                        f"   DROP {o_type} <<OLD_NAME>>; {release.HERE_STMT}\n\n")
            # rename table or stream
            return (f"--.File with {o_type} definition was renamed and *will not* be included in the release.\n"
                    f"-- [{change_type}] NOT_INCLUDED:{filename}\n\n"
                    f"   You may need to include an ALTER {o_type} RENAME statement to properly sync database state:\n"
                    f"   ALTER {o_type} <<OLD_NAME>> RENAME {o_name}; {release.HERE_STMT}\n\n")
        elif change_type == 'A':
            # add new object
            return Model._new_file_into_release_entry(change_type, easy_ddl, filename, o_name, o_type, sql)
        elif change_type == 'M':
            if easy_ddl:
                # modification / non table/stream
                return (f"--.File was changed and will be included in the release.\n"
                        f"--.You can change the order of the INCLUDE: statement below.\n"
                        f"-- [{change_type}] INCLUDED:{filename}\n\n")
            # modification / table/stream
            sql_diff = repo.get_file_diff(commit_hash, filename)
            return (f"--.File was changed but *will not be* included in the release.\n"
                    f"-- [{change_type}] NOT_INCLUDED:{filename}\n"
                    f"{sql_diff}\n"
                    f"   You may need to include an ALTER {o_type} statement to properly sync database state:\n"
                    +(f"   SELECT 1/IFF(COUNT(*)>0, 0, 1) FROM {o_name}; -- this will fail if stream is non empty\n" if o_type == 'STREAM' else '')
                    + f"   ALTER {o_type} {o_name} {release.HERE_STMT};\n\n")
        else:
            return (f"--.I don't understand this change and it it *will not* be included in the release.\n"
                    f"-- [{change_type}] NOT_INCLUDED:{filename}\n\n"
                    f"   You have to manually apply changes made in file listed above.\n"
                    f"   {release.HERE_STMT}\n\n")
    @staticmethod
    def _new_file_into_release_entry(change_type, easy_ddl, filename, o_name, o_type, sql):
        if easy_ddl:
            return (f"--.File was added and will be included in the release.\n"
                    f"--.You can change the order of the INCLUDE: statements below.\n"
                    f"-- [{change_type}] INCLUDED:{filename}\n\n")

        try:
            ddl = sf.get_ddl(repo.get_branch(), o_type, o_name)
        except RuntimeError as e:
            if 'does not exist' not in str(e):
                raise
            return (f"--.File with {o_type} definition was added and {o_name} does not exist on the server.\n"
                    f"--.It will be included in the release.\n"
                    f"--.You can change the order of the INCLUDE: statements below.\n"
                    f"-- [{change_type}] INCLUDED:{filename}\n\n")

        logger.warning(f"New CREATE {o_type} definition found in {filename}, but {o_name} already exists on the server.")
        sql_diff = get_diff_sql(ddl, sql, f"{o_type} {o_name} definition on the server",
                f"{o_type} {o_name} from {filename}")
        
        return (f"--.File with {o_type} definition was added but {o_name} *exists* on the server.\n"
                f"-- [{change_type}] NOT_INCLUDED:{filename}\n"
                f"{sql_diff}\n"
                f"   Double check if {o_type} definition on the server matches file contents. {release.HERE_STMT}\n"
                f"   SELECT '{o_type} {o_name} already exists on the server';\n\n")

model = Model()
