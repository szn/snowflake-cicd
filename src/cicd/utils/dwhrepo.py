import os
import re
from datetime import datetime

from git import Repo, InvalidGitRepositoryError

from .log import logger
from .config import config


class DWHRepo(Repo):
    """Wrapper class git git.Repo to handle DWH repository specific tasks."""
    MODEL_DIR = config.read_config('model_dir', default='model')
    SF_SAFE   = re.compile(r'\W')

    def __init__(self):
        """Inits the repo from parent folder and initialise _tags"""
        super().__init__(search_parent_directories=True)
        self._tags = sorted(self.tags, key=lambda t: t.commit.committed_datetime)

    def get_branch(self, filename_safe=True):
        """Returns active branch name as string."""
        if filename_safe:
            return self.active_branch.name.replace('/', '_')
        return self.active_branch.name

    def get_sf_safe_branch(self, branch=None):
        """Returns branch name in format safe for Snowflake object names."""
        if not branch:
            branch = self.active_branch.name
        return self.SF_SAFE.sub('_', branch).upper()

    def get_changed_files(self, index='main', prefix='', suffix='.sql',
            change_type="*"):
        """Returns all files changed from index."""
        files = {}
        for d in self.commit(index).diff():
            if d.b_path.startswith(prefix) and d.b_path.endswith(suffix) and (d.change_type in change_type or change_type == '*'):
                files[d.b_path] = d
                logger.info("  [{}] {}".format(d.change_type, d.b_path))
        return files
    
    def get_file_contents_by_commit(self, filename, commit):
        return self.git.show(f"{commit}:{filename}")

    def get_file_last_commit(self, infile):
        """Returns a three lines string description of the last change made to the file."""
        return self.git.log('-1', '--pretty= #%h%n-- change on:   %ai by %an: %s%n'
                f'-- show file:   git show %h:{infile}%n'
                f'-- last change: git diff %h^! {infile}%n', infile)
    
    def get_file_diff(self, commit, infile):
        diff = self.git.diff(commit, '--unified=0', '--abbrev', '--ignore-space-change', '--no-prefix', infile)

        diff = "\n--.DIFF: ".join(_t for _t in diff.split("\n") if not infile in _t and not _t.startswith('index ') )
        return "--.DIFF: " + diff + "\n"
    
    def diff_from_prod(self):
        diff = self.git.diff('main', '--color=always', self.MODEL_DIR)
        diff = list(filter(lambda x: not '--- a/' in x, diff.split("\n")))
        diff = list(filter(lambda x: not '+++ b/' in x, diff))
        print("\n".join(diff))

    def get_file_last_commit_hash(self, infile):
        """Returns last commit hash of the last change made to the file."""
        return self.git.log('-1', '--pretty=%H', infile)

    def assert_repo(self):
        """Checks if the repo is dirty, and if this can be allowed."""
        branch = self.get_branch()

        if self.is_dirty():
            if not self.is_model_clean():
                raise RuntimeError(f'{self.MODEL_DIR} not clean! Commit your changes.')

    def commit_release(self, release_file):
        """Adds release_file to stage and commits it."""
        self.index.add([release_file])
        self.index.commit('(DWH new release)')
        try:
            self.remote(name='origin').push()
        except (ValueError):
            logger.error('Can\'t push changes to remote!')

        
    def is_model_clean(self):
        """Logs all the changed (uncommited) files in repo."""
        model_clean = True
        if self.untracked_files:
            logger.warning('Untracked files:')
            for item in self.untracked_files:
                logger.warning('  - ' + item)
                model_clean = model_clean and not item.startswith(self.MODEL_DIR)
        if self.index.diff(None):
            logger.warning('Not commited files:')
            for item in self.index.diff(None):
                logger.warning('  - ' + item.b_path)
                model_clean = model_clean and not item.b_path.startswith(self.MODEL_DIR)
        return model_clean

    def get_dev_branches(self):
        """Returns a list of development branches and."""
        self.git.fetch("--all")
        branches = []
        for branch in self.branches:
            branches.append(self.get_sf_safe_branch(branch.name))
        return branches
    
    def get_last_commit_sha(self) -> str:
        """Returns last commit SHA (40 chars)"""
        return self.head.commit.hexsha

try:
    repo = DWHRepo()
except InvalidGitRepositoryError:
    logger.error('There is no GIT repo in this directory (or parent folders)')
    quit(-1)
