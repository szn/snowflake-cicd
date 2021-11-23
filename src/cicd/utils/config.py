import configparser

from os import path
from pathlib import Path

class Config():
    """Config wrapper that reads global config and user config."""

    PROJECT_ROOT=path.join(path.dirname(path.realpath(__file__)), '..')
    HOME_DIR=Path.home()

    def __init__(self):
        """Reads and parses global config file and user's conn file."""
        
        CONFIG_INI = path.join(Config.PROJECT_ROOT, 'config.ini')
        CONN_INI = path.join(Config.HOME_DIR, '.snowflake-cicd.ini')
        assert path.exists(CONFIG_INI), f"Missing config at path {CONFIG_INI}"
        assert path.exists(CONN_INI), f"Missing connection into at path {CONN_INI}"

        self._config = configparser.ConfigParser()
        self._config.read(CONFIG_INI)

        self._conn = configparser.ConfigParser()
        self._conn.read(CONN_INI)

    def read_config(self, key, section='default', default=None) -> str:
        """Reads [section] key from user's conn file or use global file
           if the key is missing."""
        return self._conn[section].get(key,
               self._config[section].get(key, default))

    def read_user_config(self, key, section='default', default=None) -> str:
        """Reads [section] from user .snowflake-cicd.ini file."""
        return self._conn[section].get(key, default)
    
    def sql(self, query_id) -> str:
        """Returns value from config section 'queries'."""
        return self._config['queries'].get(query_id)

config = Config()

