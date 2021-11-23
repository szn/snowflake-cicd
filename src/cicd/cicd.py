#!/usr/bin/env python3
import os
import sys
import argparse
from argparse import RawTextHelpFormatter

from .utils.model import model
from .utils.dwhrepo import repo
from .utils.log import logger, init_logger, headline
from .utils.release import release

JOBS = {}

def register_action(function):
    JOBS[function.__name__] = function.__doc__
    def wrapper(args):
        headline(function.__doc__)
        function(args)
        headline("End {}".format(function.__name__), True)
    return wrapper

@register_action
def prepare(args) -> int:
    """Prepares release candidate file."""
    model.get_all_ddls()
    model.prepare_release_candidate(force=args.force)

@register_action
def deploy(args):
    """Deploys changes from release candidate file."""
    model.deploy_release(dry_run=args.dry_run)

@register_action
def migrate(args):
    """prepare + deploy """
    prepare(args)
    deploy(args)

@register_action
def validate(args):
    """Validates all .sql files in model directory"""
    model.get_all_ddls()

@register_action
def history(args):
    """Prints release history."""
    release.print_release_history()

@register_action
def clone(args):
    """Clones (or replaces) database based on prod."""
    model.clone_production(force=args.force)

@register_action
def sync(args):
    """Syncs unapplied changes from model and releases dirs."""
    release.sync(dry_run=args.dry_run)

@register_action
def test_sync(args):
    """Test release on a separate clone (run it before creating pull request)."""
    release.test_sync()

@register_action
def compare(args):
    """Compares Snowflake and current branch DDLs."""
    if args.file:
        model.compare_single_file(filename=args.file.name)
    else: 
        model.compare_sf_git()

@register_action
def diff(args):
    """Prints diff from production."""
    repo.diff_from_prod()

@register_action
def abandoned(args):
    """Compares active branches and development clones."""
    release.compare_branches_and_clones()

def main():
    jobs = list(JOBS.keys())

    description = """  Git <-> Snowflake sync and automatic deployment. See
  README.md file for full documentation.

Actions:\n\n"""
    for job in jobs:
        description += f"  {job:10}\t\t{JOBS[job]}\n"

    parser = argparse.ArgumentParser(add_help=True,
            prog="cicd",
            formatter_class=RawTextHelpFormatter,
            description=description)
    parser.add_argument("-v", "--verbose", help="Verbose mode. Shows SQL "
                        "statements.", action="store_true")
    parser.add_argument("-t", "--dry-run", help="Show SQL to be executed, "
                        "but doesn't run it.", action="store_true")
    parser.add_argument("-f", "--force", help="Force command without yes/no "
                        "question asked in terminal.", action="store_true")
    parser.add_argument("action",  nargs='+', help="Action to run", choices=jobs)
    parser.add_argument("--file", action="store", help="Filename for compare action",
                        type=argparse.FileType('r'), nargs='?')

    if len(sys.argv)==1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    init_logger(args)

    try:
        for action in args.action:
            globals()[action](args)
    except (RuntimeError, AssertionError) as e:
        logger.error(e)
        quit(-1)

if __name__ == "__main__":
    main()
