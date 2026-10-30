"""Regression tests for native annotations, matching and binary reader support."""
from __future__ import print_function

import os
import shutil
import sys
import tempfile
import unittest

NATIVE = 0x1000000


def native(source):
    namespace = {'__name__': '__main__'}
    eval(compile(source, '<native-geoip-support>', 'exec', NATIVE, True), namespace)
    return namespace


class NativeGeoIPSupportTest(unittest.TestCase):
    def test_postponed_annotations(self):
        ns = native('''from __future__ import annotations
calls = []
def touch():
    calls.append(1)
    return int
module: UnknownType = 3
nested: dict[str, touch()] = {}
class Record:
    key: list[str]
    optional: str | None
    def method(self, value: NeverDefined) -> dict[str, int]:
        return {}
def fun(value: touch(), *, flag: bool = True) -> FutureResult:
    local: UnknownLocal
    return flag
''')
        self.assertEqual(ns['calls'], [])
        self.assertEqual(ns['__annotations__']['module'], 'UnknownType')
        self.assertIn('touch()', ns['__annotations__']['nested'])
        self.assertEqual(ns['Record'].__annotations__['key'], 'list[str]')
        self.assertEqual(ns['Record'].__annotations__['optional'], 'str | None')
        self.assertEqual(ns['fun'].__annotations__['return'], 'FutureResult')
        self.assertTrue(ns['fun'](1))
        self.assertTrue(ns['fun'].__code__.co_flags & 0x10000000)

    def test_annotations_without_future_evaluate(self):
        ns = native('''calls = []
def touch():
    calls.append(1)
    return int
def f(a: touch()):
    pass
''')
        self.assertEqual(ns['calls'], [1])
        self.assertIs(ns['f'].__annotations__['a'], int)

    def test_match(self):
        ns = native('''calls = []
def subject(value):
    calls.append(value)
    return value
class Constants:
    value = 9
def run(value):
    match subject(value):
        case None:
            return 'none'
        case True:
            return 'true'
        case 2 | 3 | 4:
            return 'or'
        case -1:
            return 'negative'
        case Constants.value:
            return 'value'
        case 8 as captured if captured > 10:
            return 'guard'
        case other if other == 8:
            return other + 1
        case _:
            return 'default'
match = 17
case = 18
results = [run(v) for v in [None, True, 1, 2, 4, -1, 9, 8, 50]]
''')
        self.assertEqual(ns['results'], ['none', 'true', 'default', 'or', 'or',
                                         'negative', 'value', 9, 'default'])
        self.assertEqual(len(ns['calls']), 9)
        self.assertEqual(ns['match'] + ns['case'], 35)

    def test_match_rejects_invalid_patterns(self):
        for source in [
            'match 1:\n    case _:\n        pass\n    case 2:\n        pass\n',
            'match 1:\n    case x | 1:\n        pass\n',
            'match 1:\n    case 1 | x:\n        pass\n',
            'match 1:\n    case x as x:\n        pass\n',
            'match 1:\n    case [x, y]:\n        pass\n',
            'match 1:\n    case len(x):\n        pass\n',
        ]:
            with self.assertRaises(SyntaxError):
                native(source)

    def test_binary_operations(self):
        ns = native('''data = b'\x01\xff'
first = data[0]
last = data[-1]
values = list(data)
text = 'ab'[0]
slice_value = data[:1]
big = int.from_bytes(data, 'big')
little = int.from_bytes(data, 'little')
signed = int.from_bytes(b'\xff', 'big', signed=True)
wide = int.from_bytes(b'\xff' * 16, 'big')
empty = int.from_bytes(b'', 'big')
iterable = int.from_bytes([1, 0], 'big')
view = int.from_bytes(memoryview(b'\x01\x00'), 'big')
'''.replace('\x01', '\\x01').replace('\xff', '\\xff').replace('\x00', '\\x00'))
        self.assertEqual((ns['first'], ns['last'], ns['values']), (1, 255, [1, 255]))
        self.assertEqual(ns['text'], 'a')
        self.assertEqual(ns['slice_value'], b'\x01')
        self.assertEqual((ns['big'], ns['little'], ns['signed']), (511, 65281, -1))
        self.assertEqual(ns['wide'], 2 ** 128 - 1)
        self.assertEqual((ns['empty'], ns['iterable'], ns['view']), (0, 256, 256))
        self.assertEqual(b'\x01'[0], b'\x01')
        self.assertEqual(list(b'ab'), ['a', 'b'])
        for expr, error in [
            ("int.from_bytes(b'x', 'invalid')", ValueError),
            ("int.from_bytes([256], 'big')", ValueError),
            ("int.from_bytes('text', 'big')", TypeError),
            ("int.from_bytes(3, 'big')", TypeError),
            ("int.from_bytes(b'x', 'big', True)", TypeError),
        ]:
            with self.assertRaises(error):
                native('value = ' + expr)

    def test_generic_alias_and_union(self):
        ns = native('''alias = dict[str, int]
origin = alias.__origin__
args = alias.__args__
instance = list[int]([1, 2])
union = int | str
optional = int | None
''')
        self.assertIs(ns['origin'], dict)
        self.assertEqual(ns['args'], (unicode, int))
        self.assertEqual(ns['instance'], [1, 2])
        self.assertEqual(ns['union'].__args__, (int, unicode))
        self.assertEqual(ns['optional'].__args__, (int, type(None)))

    def test_dataclass_keyword_only_and_frozen(self):
        ns = native('''from __future__ import annotations
from dataclasses import dataclass, field
@dataclass
class Base:
    a: int
@dataclass(kw_only=True, frozen=True)
class Frozen:
    b: int
    c: str = 'ok'
@dataclass(kw_only=True)
class Child(Base):
    b: int = 2
    c: int = field(default=3, kw_only=False)
instance = Frozen(b=4)
child = Child(1, 5, b=6)
''')
        self.assertEqual(ns['instance'].b, 4)
        self.assertEqual((ns['child'].a, ns['child'].b, ns['child'].c), (1, 6, 5))
        with self.assertRaises(TypeError):
            ns['Frozen'](4)
        from dataclasses import FrozenInstanceError
        with self.assertRaises(FrozenInstanceError):
            ns['instance'].b = 9

    def test_native_recursion_error(self):
        ns = native('''import sys
saved = sys.getrecursionlimit()
def recurse():
    return recurse()
caught = False
try:
    sys.setrecursionlimit(60)
    try:
        recurse()
    except RecursionError:
        caught = True
finally:
    sys.setrecursionlimit(saved)
''')
        self.assertTrue(ns['caught'])
        self.assertTrue(issubclass(RecursionError, RuntimeError))
        self.assertIsNot(RecursionError, RuntimeError)

    def test_date_fromisoformat(self):
        from datetime import date
        self.assertEqual(date.fromisoformat(u'2024-02-29'), date(2024, 2, 29))
        self.assertEqual(date.fromisoformat(u'2025-04-14').isoformat(), '2025-04-14')
        class Day(date):
            pass
        self.assertIsInstance(Day.fromisoformat('2025-04-14'), Day)
        for text in ('2023-02-29', '2025-4-14', '2025/04/14', '0000-01-01',
                     '2025-04-14x', '20250414'):
            with self.assertRaises(ValueError):
                date.fromisoformat(text)
        with self.assertRaises(TypeError):
            date.fromisoformat(None)

    def test_match_ast_and_suspension(self):
        import ast
        code = '''def run(value):
    match value:
        case 1 as captured if (yield 'guard'):
            yield captured
        case _:
            yield 'fallback'
'''
        tree = compile(code, '<match-ast>', 'exec', NATIVE | 1024, True)
        self.assertIsInstance(tree.body[0].body[0], ast.Match)
        self.assertIsInstance(tree.body[0].body[0].cases[0].pattern, ast.MatchAs)
        namespace = {}
        eval(compile(tree, '<match-ast>', 'exec', NATIVE, True), namespace)
        iterator = namespace['run'](1)
        self.assertEqual(next(iterator), 'guard')
        self.assertEqual(iterator.send(True), 1)
        with self.assertRaises(StopIteration):
            next(iterator)
        iterator = namespace['run'](1)
        next(iterator)
        self.assertEqual(iterator.send(False), 'fallback')

    def test_distribution_metadata(self):
        from importlib.metadata import version, requires, PackageNotFoundError
        directory = tempfile.mkdtemp()
        sys.path.insert(0, directory)
        try:
            metadata = os.path.join(directory, 'demo_pkg-1.2.3.dist-info')
            os.mkdir(metadata)
            with open(os.path.join(metadata, 'METADATA'), 'w') as stream:
                stream.write('Name: Demo_Pkg\nVersion: 1.2.3\nRequires-Dist: example>=1\n')
            self.assertEqual(version('demo-pkg'), '1.2.3')
            self.assertEqual(requires('DEMO.PKG'), ['example>=1'])
            with self.assertRaises(PackageNotFoundError):
                version('nonexistent-distribution-for-jython-test')
        finally:
            sys.path.remove(directory)
            shutil.rmtree(directory)

    def test_class_keywords(self):
        ns = native('''from abc import ABCMeta, abstractmethod
calls = []
class Meta(type):
    @classmethod
    def __prepare__(mcls, name, bases, *, label):
        calls.append(('prepare', label))
        return {'prepared': label}
    def __new__(mcls, name, bases, namespace, *, label):
        calls.append(('new', namespace['prepared']))
        return type.__new__(mcls, name, bases, namespace)
    def __init__(cls, name, bases, namespace, *, label):
        pass
class Prepared(metaclass=Meta, **{'label': 'ok'}):
    value = prepared
class Abstract(metaclass=ABCMeta):
    @abstractmethod
    def method(self):
        pass
class Concrete(Abstract):
    def method(self):
        return __class__.__name__
class OldMarker:
    __metaclass__ = ABCMeta
''')
        self.assertEqual(ns['calls'], [('prepare', 'ok'), ('new', 'ok')])
        self.assertEqual(ns['Prepared'].value, 'ok')
        self.assertEqual(ns['Concrete']().method(), 'Concrete')
        self.assertIs(type(ns['OldMarker']), type)
        with self.assertRaises(TypeError):
            ns['Abstract']()
        with self.assertRaises(TypeError):
            native("class Bad(metaclass=type, **{'metaclass': type}): pass")
        with self.assertRaises(TypeError):
            native("class Bad(**{1: type}): pass")
        with self.assertRaises(TypeError):
            native('''class Left(type): pass
class Right(type): pass
class A(metaclass=Left): pass
class B(metaclass=Right): pass
class Bad(A, B): pass
''')

    def test_contextlib_suppress(self):
        from contextlib import suppress
        with suppress(ValueError):
            raise ValueError('expected')
        with self.assertRaises(TypeError):
            with suppress(ValueError):
                raise TypeError('must escape')


if __name__ == '__main__':
    unittest.main()
