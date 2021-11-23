import os
import re
from datetime import datetime

from .config import config
from .log import logger, is_debug
from .utils import get_file_contents, hexDigest, remove_file
from .dwhrepo import repo
from .snowflake import sf
from .sql import sql_meta, print_sql

class Release():
    """Performs releases and handles release files."""
    RELEASES_DIR       = config.read_config('releases_dir', default='releases')
    MODEL_DIR          = config.read_config('model_dir', default='model')
    RELEASE_CANDIDATE  = os.path.join(RELEASES_DIR, 'release_candidate.sql')
    RELEASE_SHA        = os.path.join(RELEASES_DIR, 'release_candidate.sha')
    RELEASE_TABLE      = 'PUBLIC.DWH_RELEASES_HISTORY'
    INCLUDED           = re.compile(r'-- \[(?P<change>.)\] (?P<inc>(NOT_)?INCLUDED):(?P<file>{}/\S+)( #)?(?P<hash>\S+)?'.format(MODEL_DIR))
    HERE_STMT          = '<<HERE>>'

    def __init__(self):
        self.sf_safe_branch  = repo.get_sf_safe_branch()

    def check_release_candidate(self):
        """Asserts if release candidate file existis and was not modified."""
        if self.release_candidate_exists():
            if self.release_candidate_modified():
                raise RuntimeError("{} was changed or you changed branch, can't create new "
                        "release candidate.\nEither remove it, allow me to do so by adding --force flag, or deploy it.".format(self.RELEASE_CANDIDATE))
            logger.info("Release candidate file exists, but it was not modified. Will be replaced.")

    def release_candidate_modified(self):
        """Returns bool if release candidate file was manually modified."""
        if not os.path.exists(self.RELEASE_SHA):
            raise RuntimeError("Release candidate file {} exists but MD5 sum file is missing.".format(self.RELEASE_CANDIDATE))
        branch = repo.get_branch()
        rc_file_hash = hexDigest(get_file_contents(self.RELEASE_CANDIDATE) + branch)
        rc_stored_md5 = get_file_contents(self.RELEASE_SHA)
        
        return rc_file_hash != rc_stored_md5

    def get_release_candidate_lines(self):
        """Returns release candidate file contents as lines."""
        with open(self.RELEASE_CANDIDATE, 'r') as release_candidate_file:
            return release_candidate_file.readlines()
    
    def check_release_dir_clean(self, base_commit) -> None:
        """Checks if all the release files were applied in current DB."""
        files_added = self.get_unsynced_releases(base_commit)

        if len(files_added) > 0:
            raise RuntimeError("Files present in {} folder that were not applied on the "
                    "database.\nYou have to 'sync' first.".format(self.RELEASES_DIR))

    def sync(self, branch=None, dry_run=False) -> None:
        """Syncs non-applied changes in releases and model folders."""
        if branch is None:
            branch = self.sf_safe_branch

        commit_hash = self.get_base_commit(branch)
        files = self.get_unsynced_releases(commit_hash)

        if files.values():
            logger.warning("Syncing changes:")
        else:
            logger.info("No pending changes to sync.")
        for change in files.values():
            if change.change_type == 'D':
                logger.warning(f"Skipping removed release file {change.a_path}.")
                continue

            changed_file = change.b_path
            logger.info("Running release file {}:".format(changed_file))

            deploy_sql = self.release_file_to_sql(get_file_contents(changed_file))

            if is_debug():
                print_sql(deploy_sql)
            if dry_run:
                if not is_debug():
                    print_sql(deploy_sql)
                logger.info("Skipping SQL execution due to --dry-run.")
                return

            sf.perform_release(deploy_sql, branch)
            self.insert_release_entry(changed_file, branch)
    
    def test_sync(self):
        last_commit_sha = repo.get_last_commit_sha()
        sf.clone_production(branch=last_commit_sha, force=True)
        try:
            release.sync(branch=last_commit_sha)
        except Exception as e:
            raise
        finally:
            sf.drop_clone(branch=last_commit_sha)

    def save_release(self, sql):
        """Save release file (if needed) commits it and adds new entry in
           DWH changelog table."""

        release_filename = self._gen_release_filename()
        logger.info(f'Writing to {release_filename}.')
        with open(release_filename, 'a+') as release_file:
            release_file.write(sql)

        repo.commit_release(release_filename)

        self.insert_release_entry(release_filename, self.sf_safe_branch)
        self.remove_release_candidate()

    def remove_release_candidate(self):
        """Removes release candidate files."""
        if self.release_candidate_modified():
            logger.warning(f'Removing modified release candidate file {self.RELEASE_CANDIDATE}.')
        else:
            logger.info(f'Removing release candidate file {self.RELEASE_CANDIDATE}.')

        remove_file(self.RELEASE_CANDIDATE)
        remove_file(self.RELEASE_SHA)

    def release_candidate_exists(self):
        """Checks if release candidate file exists."""
        return os.path.exists(self.RELEASE_CANDIDATE)

    def save_release_candidate_file(self, sql, branch):
        """Saves release candidate file and MD5 sum file."""
        with open(self.RELEASE_CANDIDATE, 'w') as release_candidate_file:
            release_candidate_file.write(sql)
        with open(self.RELEASE_SHA, 'w') as release_candidate_md5:
            # by including branch in hash we ensure noone will run release candidate
            # from branch "A" after switching to branch "B"
            release_candidate_md5.write(hexDigest(sql + branch))
        
        logger.info(f"{self.RELEASE_CANDIDATE} and {self.RELEASE_SHA} created.")

    def print_release_history(self):
        """Returns release history."""
        release_history = self.release_history(self.sf_safe_branch)
        logger.info("|{:_^13}|{:_^32.32}|{:_^22}|{:_^18}|{:_^6}|{:_^6}|".format(
            'commit hash', 'file name', 'applied by', 'applied on', 'branch', 'prod'))
        for rel in release_history:
            logger.info("| {:>10.10}  | {:<30.30} | {:^20.20} | {:%Y-%m-%d %H:%M} | {:^4} | {:^4} |".format(
                rel[0], str(rel[1])[-30:], rel[2], rel[3], '•' if rel[4] else '', '•' if rel[5] else ''))

    def release_history(self, branch):
        """Returns release history from DB."""
        sql = config.sql('release_history').format(
            RELEASE_TABLE=self.RELEASE_TABLE, SF_PROD_NAME=sf.SF_PROD_NAME)
        history = sf.run_single_statament(sql, branch)
        return history

    def get_base_commit(self, branch):
        """Queries the based commit in release history table."""
        
        sql = config.sql('get_base_commit').format(RELEASE_TABLE=self.RELEASE_TABLE)
        commit = sf.run_single_statament(sql, branch)
        assert len(commit) > 0, "No data in release history table, you need to create an initial entry"
        logger.debug("Base commit hash in current database is {}."
                .format(commit[0][0]))
        return commit[0][0]

    def insert_release_entry(self, filename, branch):
        """Inserts a row in a release history table."""
        commit = repo.get_file_last_commit_hash(filename)

        sql = config.sql('insert_release_entry').format(
            RELEASE_TABLE=self.RELEASE_TABLE, commit=commit, filename=filename)
        sf.run_single_statament(sql, branch)
        logger.info("New entry in release history table with {}"
                .format(commit))

    def release_candidate_contains(self, contains):
        """Checks if specific entry is present in the release history file."""
        file_contents = get_file_contents(self.RELEASE_CANDIDATE)
        return contains in file_contents

    def prepare_release_file(self):
        """Deploys a release based on existing release candidate file."""
        if not self.release_candidate_exists():
            raise RuntimeError("Release candidate file does not exist, can't "
                    "make a release. Prepare release first.")

        if self.release_candidate_contains(self.HERE_STMT):
            raise RuntimeError(f"Code placeholder ({self.HERE_STMT}) found in the release "
                    "candidate file. Replace it with a valid SQL statement "
                    "or remove the line.")

        branch = repo.get_branch()
        user = config.read_user_config('user')

        release_sql = "\n-- RELEASE FROM BRANCH {}\n-- {} on {:%Y-%m-%d %H:%M}\n\n".format(
            branch, user, datetime.now())

        for line in release.get_release_candidate_lines():
            if line.startswith('--.'):
                continue
        
            included = self.INCLUDED.search(line)    
            if included and included.group('change') != 'D':
                release_sql += line.strip()
                release_sql += repo.get_file_last_commit(included.group('file'))
                continue
            
            release_sql += line
        
        return release_sql

    def release_file_to_sql(self, release_sql) -> str:
        """Converts release file (with filenames) to SQL."""
        sql = ""
        for line in release_sql.splitlines():
            included = self.INCLUDED.search(line)
            logger.debug(line)
            if included:
                sql += line + "\n"
                if included.group('inc') == 'INCLUDED':
                    sql += repo.get_file_contents_by_commit(included.group('file'), included.group('hash'))

            if not line.startswith('--'):
                sql += line + "\n"

        return sql
    
    def get_unsynced_releases(self, base_commit):
        """Returns list with unsynced releases."""
        return repo.get_changed_files(index=base_commit,
                prefix=self.RELEASES_DIR, change_type=('A', 'R', 'M'))
    
    def compare_branches_and_clones(self) -> None:
        branches = repo.get_dev_branches()
        branches = list(map(lambda x: sf.get_db_name(x), branches))
        
        clones = sf.get_dev_clones()
        logger.info("|{:_^30}|{:_^18}|{:_^18}|{:_^14}|".format(
            'clone', 'created', 'updated', 'has branch?'))
        for clone in clones:
            logger.info("| {:<28.28} | {:%Y-%m-%d %H:%M} | {:%Y-%m-%d %H:%M} | {:^12} |".format(
                clone[0], clone[1], clone[2], 'yes' if clone[0] in branches else 'no'))

    def _gen_release_filename(self) -> str:
        """Generates release filename based on branch."""
        base = repo.get_branch()
        filebase = os.path.join(self.RELEASES_DIR, base)
        return f"{filebase}.sql"


release = Release()
