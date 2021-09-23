import configparser

from os import path

class Config():
    """Config wrapper that reads global config and user config."""

    PROJECT_ROOT=path.join(path.dirname(path.realpath(__file__)), '..')

    def __init__(self):
        """Reads and parses global config file and users conn file."""
        self._config = configparser.ConfigParser()
        self._config.read(path.join(self.PROJECT_ROOT, 'config.ini'))
        self._conn = configparser.ConfigParser()
        self._conn.read('.conn.ini')

    def read_config(self, key, section='default', default=None) -> str:
        """Reads [section] key from user's conn file or use global file
           if the key is missing."""
        return self._conn[section].get(key,
               self._config[section].get(key, default))

    def read_user_config(self, key, section='default', default=None) -> str:
        """Reads [section] from user .conn.ini file."""
        return self._conn[section].get(key, default)
    
    def sql(self, query_id) -> str:
        """Returns value from config section 'queries'."""
        return self._config['queries'].get(query_id)

config = Config()

