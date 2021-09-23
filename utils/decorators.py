from functools import wraps
from time import time

indent = 2
space = ' '


def timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        global indent, space
        print(f'{space: <{indent}}func:{f.__name__} args:[{args}, {kw}] started')
        indent += 2
        ts = time()
        result = f(*args, **kw)
        te = time()
        indent -= 2
        print(f'{space: <{indent}}func:{f.__name__} finished: {te-ts:2.4f} sec')
        return result
    return wrap
