import os

import hashlib

def get_file_contents(filename):
    """Returns file content as string."""
    with open(filename, 'r') as srcfile:
        return srcfile.read()

def hexDigest(string):
    """Returns md5 hash from s parameter."""
    return hashlib.md5(string.encode()).hexdigest()

def remove_file(filename):
    """Removes the file (if the file exist)."""
    if os.path.exists(filename):
        os.remove(filename)

def yes_or_no(question):
    while "the answer is invalid":
        reply = str(input(question+' (y/n): ')).lower().strip()
        if reply[:1] == 'y':
            return True
        if reply[:1] == 'n':
            return False
