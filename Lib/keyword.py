"""Keywords accepted by Jython's transitional native grammar.

Python 2 keywords remain reserved while its standard library is in use.
Keep this list synchronized with grammar/Python.g when migrating syntax.
"""

__all__ = ['iskeyword', 'kwlist']

kwlist = [
    'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del',
    'elif', 'else', 'except', 'exec', 'finally', 'for', 'from', 'global',
    'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
    'print', 'raise', 'return', 'try', 'while', 'with', 'yield',
]

iskeyword = frozenset(kwlist).__contains__
