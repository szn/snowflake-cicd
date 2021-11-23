import logging

import coloredlogs
from termcolor import colored

logger = logging.getLogger("snowflake.cicd")

def init_logger(args=None):
    coloredlogs.install(
            level='DEBUG' if args and args.verbose else 'INFO',
            logger=logger,
            fmt='%(asctime)s %(programname)s %(message)s',
            programname='>',
            datefmt='%H:%m:%S',
            field_styles= {
                    'asctime': {'color': 'black', 'bright': True},
                    'hostname': {'color': 'magenta'},
                    'levelname': {'bold': True, 'color': 'black'},
                    'name': {'color': 'blue'},
                    'programname': {'color': 'black', 'bright': True},
                    'username': {'color': 'yellow'}},
            level_styles= {
                    'critical': {'bold': True, 'color': 'red'},
                    'debug': {'color': 'white', 'faint': True},
                    'error': {'color': 'red'},
                    'info': {'color': 'white', 'faint': False},
                    'notice': {'color': 'magenta'},
                    'warning': {'color': 'yellow'}})

    logging.getLogger("snowflake.connector.network").disabled = False
    logging.getLogger("snowflake.cicd").level = logging.DEBUG if args and args.verbose else logging.INFO

def is_debug():
    return logger.level <= logging.DEBUG

def headline(msg, end=False):
    if end:
        logger.info(colored("{:>50}  ".format(msg), 'white',
                attrs=['reverse', 'dark']))
    else:
        logger.info(colored("  {:50}".format(msg), 'white',
                attrs=['reverse']))
