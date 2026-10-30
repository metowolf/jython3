"""Runtime type expressions for the opt-in native dialect.

This is a bounded GenericAlias/union implementation, not a replacement for
all typing introspection and type-variable substitution.
"""


def _name(value):
    if value is type(None):
        return 'None'
    if isinstance(value, type):
        module = value.__module__
        return ('' if module in ('__builtin__', 'builtins') else module + '.') + value.__name__
    return repr(value)


class GenericAlias(object):
    def __init__(self, origin, args):
        self.__origin__ = origin
        self.__args__ = args if isinstance(args, tuple) else (args,)

    def __call__(self, *args, **kwargs):
        return self.__origin__(*args, **kwargs)

    def __repr__(self):
        return '%s[%s]' % (_name(self.__origin__), ', '.join(_name(x) for x in self.__args__))

    def __eq__(self, other):
        return (isinstance(other, GenericAlias) and self.__origin__ == other.__origin__
                and self.__args__ == other.__args__)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.__origin__, self.__args__))

    def __or__(self, other):
        return union(self, other)

    def __ror__(self, other):
        return union(other, self)


class UnionType(object):
    def __init__(self, args):
        self.__args__ = args

    def __repr__(self):
        return ' | '.join(_name(x) for x in self.__args__)

    def __eq__(self, other):
        return isinstance(other, UnionType) and frozenset(self.__args__) == frozenset(other.__args__)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(frozenset(self.__args__))

    def __or__(self, other):
        return union(self, other)

    def __ror__(self, other):
        return union(other, self)


def union(left, right):
    values = []
    for value in (left, right):
        if value is None:
            value = type(None)
        if not isinstance(value, (type, GenericAlias, UnionType)):
            return NotImplemented
        for item in value.__args__ if isinstance(value, UnionType) else (value,):
            if item not in values:
                values.append(item)
    return values[0] if len(values) == 1 else UnionType(tuple(values))
