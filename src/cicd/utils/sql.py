import re
from io import StringIO

import sqlparse
from termcolor import colored, cprint

from .utils import get_file_contents
from .log import logger

TABLE_DIR    = re.compile(r'/tables?/', re.I)
CREATE_TABLE = re.compile(r'create\s+((or\s+replace\s+)|(if\s+not\s+exists\s+))?table', re.I)

OR_REPLACE   = re.compile(r'create\s+or\s+replace\s+', re.I)
IF_NOT_EXISTS= re.compile(r'create\s+if\s+not\s+exists\s+', re.I)

OBJECT_TYPE  = (r'procedure|function|table|external\s+table|sequence|'
                r'view|materialized\s+view|file\s+format|stage|pipe|stream|task')
TYPE         = re.compile(OBJECT_TYPE, re.I)
TYPE_NAME    = re.compile(r'create\s+(or\s+replace\s+)?(if\s+not\s+exists\s+)?'
                          r'(local\s+|global\s+)?(temp\s+|temporary\s+|volatile\s+)?(transient\s+)?'
                          r'(?P<o_type>' + OBJECT_TYPE + r')\s+(?P<o_name>[\.\w-]+)', re.I)
DROP         = re.compile(r'drop\s+(' + OBJECT_TYPE + ')', re.I)

TYPE_DIR     = re.compile(r'/(?P<dir_type>' + OBJECT_TYPE.replace(r'\s+', '.') + r')s?/')

RESUME_TASK  = re.compile(r"alter\s+task\s+[\.\w-]+\s+resume\s*;",re.I)

_print_comment   = lambda x: cprint(x, 'green', attrs=['dark'], end='')
_print_keyword   = lambda x: cprint(x.upper(), 'blue', end='')
_print_other     = lambda x: cprint(x, 'white', end='')


def print_sql(sql):
    """Pretty prints SQL."""
    res = sqlparse.parse(sql)
    for r in res:
        for st in r:
            if type(st) == sqlparse.sql.Comment or str(st.ttype).startswith('Token.Comment'):
                _print_comment(st.value)
            elif st.is_keyword:
                _print_keyword(st.value)
            else:
                _print_other(st.value)
    print("\n")

def split_sql(sql):
    """Splits given SQL into list of statements, stripping comments."""
    sql = sqlparse.format(sql, strip_comments=True)
    return sqlparse.split(sql)

def sql_meta(filename):
    dir_type = TYPE_DIR.search(filename)
    assert dir_type, (f"Can't find valid object type prefix\nin {filename}")
    dir_type = dir_type.group('dir_type')

    sql = get_file_contents(filename)
    type_name = TYPE_NAME.search(sql)
    assert type_name, (f"Can't find a valid SQL CREATE statement\nin {filename}")

    o_type = type_name.group('o_type').upper().replace(' ', '_')
    o_name = type_name.group('o_name').upper()

    if dir_type.upper() != o_type:
        logger.warning(f"SQL CREATE {o_type} statement in folder named {dir_type}\nin{filename}")
    
    easy_ddl = False if o_type in ['TABLE', 'STREAM'] else True

    if not easy_ddl and not IF_NOT_EXISTS.search(sql):
        logger.debug(f"SQL CREATE {o_type} statement without 'IF NOT EXISTS' statement\nin {filename}")
    
    assert easy_ddl or not OR_REPLACE.search(sql), (
            f"Dangerous SQL CREATE {o_type} statement with 'OR REPLACE' statement\nin {filename}")
    
    assert easy_ddl or not DROP.search(sql), (
            f"Dangerous SQL DROP {o_type} statement\nin {filename}")

    if easy_ddl and not OR_REPLACE.search(sql):
        logger.warning(f"SQL CREATE {o_type} statement without 'OR REPLACE' statement\nin {filename}")
    
    return (o_name, o_type, easy_ddl, sql)

def get_diff_sql(left, right, fromfile, tofile):
    left = sqlparse.format(left, strip_comments=True)
    right = sqlparse.format(right, strip_comments=True)
    left = StringIO(left).readlines()
    right = StringIO(right).readlines()

    from difflib import unified_diff

    return "--.DIFF: " + "--.DIFF: ".join(unified_diff(left, right, fromfile=fromfile, tofile=tofile))        

def statement_cleanup(statement) -> str:
    """ Cleans up SQL statement. """
    statement = sqlparse.format(statement, strip_comments=True, keyword_case='lower',
                                identifier_case='lower')
    return statement 
