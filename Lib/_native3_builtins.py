"""Builtins for CO_NATIVE3 code. The bootstrap stdlib retains Python 2 builtins."""
import __builtin__
import io
import sys
from itertools import imap, izip, ifilter


def input(prompt=''):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    value = sys.stdin.readline()
    if not value:
        raise EOFError('EOF when reading a line')
    if not isinstance(value, unicode):
        value = value.decode(getattr(sys.stdin, 'encoding', None) or 'utf-8')
    if value.endswith(u'\n'):
        value = value[:-1]
        if value.endswith(u'\r'):
            value = value[:-1]
    return value


namespace = vars(__builtin__).copy()
namespace.update(str=unicode, input=input, open=io.open, range=xrange,
                 zip=izip, map=imap, filter=ifilter)
