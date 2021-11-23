import re

import snowflake.connector as sfc
from snowflake.connector.errors import Error as SfError
from snowflake.connector.errors import DatabaseError
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import dsa
from cryptography.hazmat.primitives import serialization

from .log import logger, is_debug
from .config import config
from .sql import split_sql, print_sql, RESUME_TASK
from .utils import yes_or_no

class Snowflake():
    """Snowflake connector wrapper."""

    SF_VALID_NAME = re.compile(r'^[\w-]+$')
    SF_PROD_NAME = config.read_config('production_db')
    SF_STAGING_NAME = config.read_config('staging_db')

    def __init__(self):
        self._conn = None

    def connect(self, branch):
        """Connect to the DB and returns connection."""
        db = self.get_db_name(branch)
        key = self._get_key(config.read_user_config('private_key_file'))
        user = config.read_user_config('user')
        warehouse = config.read_config('warehouse')
        role = config.read_config('role')
        logger.debug("Connecting to Snowflake database {} as {}".format(db,
            user))
        logger.debug("Role {}, warehouse {}".format(role, warehouse))
        try:
            if not key:
                logger.warning('Connecting to Snowflake using password. Please use key-pair auth instead.')
                return sfc.connect(password=config.read_user_config('password'),
                        user=user,
                        account=config.read_config('account'),
                        warehouse=warehouse,
                        database=db,
                        autocommit=False,
                        role=role,
                        validate_default_parameters=True,
                        schema='PUBLIC')
            return sfc.connect(private_key=key,
                    user=user,
                    account=config.read_config('account'),
                    warehouse=warehouse,
                    database=db,
                    autocommit=False,
                    role=role,
                    #validate_default_parameters=True,
                    schema='PUBLIC')
        except DatabaseError as de:
            if "250001 (08001)" in str(de):
                logger.info("Is this your first run in this branch and the database was not cloned? Try 'clone' first.")
            raise RuntimeError(de)

    def perform_release(self, sql, branch):
        """Run arbitrary SQL statement(s)."""
        conn = self.connect(branch)
        skip_resume_task = (self.get_db_name(branch) != self.SF_PROD_NAME)
        cur = conn.cursor()
        try:
            cur.execute(config.sql('autocommit'))
            cur.execute(config.sql('transaction_abort'))
            logger.debug('BEGIN TRANSACTION')
            cur.execute(config.sql('transaction_begin'))
            for statement in split_sql(sql):
                if skip_resume_task and RESUME_TASK.search(statement):
                    logger.info("Skipping '{}' statement as this is not production".format(
                        statement.replace("\n", " ")))
                    continue
                logger.debug('  running statement:')
                if is_debug():
                    print_sql(statement)
                try:
                    cur.execute(statement)
                except SfError as e:
                    if 'Empty SQL statement' in str(e):
                        logger.warning("Found empty SQL statement. Too many ';' in file?")
                    else:
                        logger.error("Release failed due to this statement:")
                        print_sql(statement)
                        raise
                if cur.rowcount:
                    logger.info("  " + str(cur.fetchone())[1:-1])
            logger.debug('COMMIT TRANSACTION')
            cur.execute(config.sql('commit'))
        except SfError as e:
            logger.debug('ROLLBACK TRANSACTION')
            conn.rollback()
            logger.error('Error while running the release:')
            raise RuntimeError(e)
        finally:
            conn.close()

    def run_single_statament(self, query, branch='main'):
        """Runs single SQL statement against Snowflake."""
        conn = self.connect(branch)
        cur = conn.cursor()
        try:
            if is_debug():
                print_sql(query)
            cur.execute(query)
            conn.commit()
            return cur.fetchall()
        except SfError as e:
            conn.rollback()
            if "This session does not have a current database" in str(e):
                logger.info("Is this your first run in this branch and the database was not cloned? Try 'clone' first.")
            raise RuntimeError(e)
        finally:
            conn.close()

    def clone_production(self, branch, force=False):
        """Clones production database into new db named after branch name."""
        newdb = self.get_db_name(branch)
        assert self.SF_VALID_NAME.match(newdb), (f"{newdb} is not a valid Snowflake"
                " identifier")
        assert newdb.strip().upper() != self.SF_PROD_NAME, ("Trying to create new database"
                f" with name {self.SF_PROD_NAME} (which is production db name!)")     
        assert newdb.strip().upper() != self.SF_STAGING_NAME or force, (
                f"Trying to recreate {self.SF_STAGING_NAME} without --force.")
        
        if not force:
            logger.info(f"Checking if {newdb} already exists...")
            sql = config.sql('clone_exists').format(newdb=newdb)
            clone_exists = self.run_single_statament(sql)
        
            if clone_exists[0][0] != 0 and not yes_or_no(f"{newdb} already exists. Are you sure you want to replace it"):
                return

        logger.info(f"Cloning {self.SF_PROD_NAME} into {newdb}")

        sql = config.sql('create_clone').format(newdb=newdb, prod=self.SF_PROD_NAME)
        self.run_single_statament(sql)
        logger.info("Cloning finished")
    
    def drop_clone(self, branch, force=False):
        """Drops clone."""
        db = self.get_db_name(branch)
        assert self.SF_VALID_NAME.match(db), (f"{db} is not a valid Snowflake"
                " identifier")
        assert db.strip().upper() != self.SF_PROD_NAME, ("Never ever drop production!")     
        assert db.strip().upper() != self.SF_STAGING_NAME or force, (
                f"Trying to drop {self.SF_STAGING_NAME} without --force.")
        
        logger.info(f"Dropping clone {db}")

        self.run_single_statament(f'DROP DATABASE {db};')
        logger.info("Dropping clone finished")

    def get_dev_clones(self):
        """Returns all development clones""" 
        sql = config.sql('get_dev_clones')
        return self.run_single_statament(sql)
    
    def get_altered_objects(self, branch):
        """Returns all objects changed since clone creation."""
        db = self.get_db_name(branch)
        sql = config.sql('get_altered_objects').format(db=db)
        return self.run_single_statament(sql, branch)
    
    def get_all_objects(self, branch):
        db = self.get_db_name(branch)
        sql = config.sql('get_all_objects').format(db=db)
        all_objects = self.run_single_statament(sql, branch)

        sql = config.sql('get_streams').format(db=db)
        streams = self.run_single_statament(sql, branch)
        for stream in streams:
            all_objects += [(stream[3], stream[1], 'STREAM', stream[0])]

        sql = config.sql('get_tasks').format(db=db)
        tasks = self.run_single_statament(sql, branch)
        for task in tasks:
            all_objects += [(task[4], task[1], 'TASK', task[0])]
        
        dictionary = {}
        for obj in all_objects:
            dictionary[(obj[2] + '#' + obj[0] + '.' + obj[1]).upper()] = (obj[0] + '.' + obj[1], obj[2], obj[3])

        return dictionary
    
    def get_ddl(self, branch, o_type, o_name) -> str:
        """Returns object DDL."""
        sql = config.sql('get_ddl').format(o_type=o_type, o_name=o_name,
                                           parameters="()" if o_type=="PROCEDURE" else "")
        return self.run_single_statament(sql, branch)[0][0]

    def get_db_name(self, branch):
        """Converts branch name into database name to operate on."""
        if(branch.upper() == 'MAIN'):
            return self.SF_PROD_NAME
        elif(branch.upper() == 'DEVELOP'):
            return self.SF_STAGING_NAME
        else:
            return '_DEV_' + branch.upper()[:30]

    def _get_key(self, keypath):
        """Converts PKCS8 file into bytes array acceptable by Snowflake connector."""
        with open(keypath, "rb") as key:
            p_key = serialization.load_pem_private_key(
                    key.read(),
                    password=None,
                    backend=default_backend())
            return p_key.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption())

sf = Snowflake()
