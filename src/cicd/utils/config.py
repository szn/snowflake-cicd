import configparser
import functools

from os import path
from pathlib import Path

class Config():
    """Config wrapper that reads global config and user config."""

    PROJECT_ROOT = path.join(path.dirname(path.realpath(__file__)), '..')
    CONFIG_INI = path.join(PROJECT_ROOT, 'config.ini')
    HOME_DIR = Path.home()
    CONN_INI = path.join(HOME_DIR, '.snowflake-cicd.ini')

    def __init__(self):
        pass
    
    def __lazy_init(func):
        """Reads and parses global config file and user's conn file."""
        @functools.wraps(func)
        def wrap(self, *args, **kwargs):
            if not hasattr(self, '_config'):
                assert path.exists(Config.CONFIG_INI), f"Missing config file at path {Config.CONFIG_INI}"
                self._config = configparser.ConfigParser()
                self._config.read(Config.CONFIG_INI)

            if not hasattr(self, '_conn'):
                assert path.exists(Config.CONN_INI), f"Missing connection settings file at path {Config.CONN_INI}"
                self._conn = configparser.ConfigParser()
                self._conn.read(Config.CONN_INI)

            return func(self, *args, **kwargs)
        return wrap

    @__lazy_init
    def read_config(self, key, section='default', default=None) -> str:
        """Reads [section] key from user's conn file or use global file
           if the key is missing."""
        return self._conn[section].get(key,
               self._config[section].get(key, default))

    @__lazy_init
    def read_user_config(self, key, section='default', default=None) -> str:
        """Reads [section] from user .snowflake-cicd.ini file."""
        return self._conn[section].get(key, default)
    
    @__lazy_init
    def sql(self, query_id) -> str:
        """Returns value from config section 'queries'."""
        return self._config['queries'].get(query_id)

config = Config()
