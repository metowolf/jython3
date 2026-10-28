# -*- coding: utf-8 -*-
"""Native PEP 498 f-strings and Python 3.8 debug fields.

Shared semantics run on both the migrating Jython runtime and CPython 3.11.
"""
from __future__ import unicode_literals

import ast
import codeop
from datetime import datetime, timedelta
import sys
import time
import unittest

IS_JYTHON = sys.platform.startswith('java')


class FStringTest(unittest.TestCase):
    def test_basic(self):
        name, year = 'Python', 1991
        self.assertEqual(f'{name}: {year}', 'Python: 1991')
        self.assertEqual(f'{True} {None} {1 + 2}', 'True None 3')
        self.assertEqual(f'', '')
        self.assertEqual(f'constant', 'constant')
        self.assertEqual(type(f'{year}'), type(u''))

    def test_boolean_formats(self):
        self.assertEqual(f'{True:} {False:}', 'True False')
        self.assertEqual(f'{True!s} {False!r} {True!a}', 'True False True')
        self.assertEqual(f'{True:04d} {False:04d}', '0001 0000')

    def test_prefixes_and_quotes(self):
        for prefix in ('f', 'F', 'fr', 'fR', 'Fr', 'FR', 'rf', 'rF', 'Rf', 'RF'):
            for quote in ("'", '"', "'''", '"""'):
                source = prefix + quote + '{value}' + quote
                self.assertEqual(eval(source, {'value': 7}), '7')

    def test_braces(self):
        value = 4
        self.assertEqual(f'{{}} {{{value}}} {{{{x}}}}', '{} {4} {{x}}')
        self.assertEqual(f'{{{value:03d}}}', '{004}')
        self.assertEqual(f'{{x}}', '{x}')

    def test_escapes(self):
        value = 7
        self.assertEqual(f'\n{value}\t\x41\u4e2d\U0001f600', '\n7\tA中😀')
        self.assertEqual(f'\N{LEFT CURLY BRACKET}{value}\N{RIGHT CURLY BRACKET}', '{7}')
        self.assertEqual(f'\x7bvalue\x7d', '{value}')
        self.assertEqual(eval(r"f'\{value}'", {'value': value}), '\\7')
        self.assertEqual(f'\\{value}', '\\7')
        self.assertEqual(f'ab\
cd{value}', 'abcd7')

    def test_raw(self):
        value = 7
        self.assertEqual(rf'\n{value}\u4e2d', '\\n7\\u4e2d')
        self.assertEqual(fr'\{value}', '\\7')
        self.assertEqual(rf'\N{value}', '\\N7')

    def test_unicode(self):
        value = u'中文😀'
        self.assertEqual(f'原始对象: {value}', '原始对象: 中文😀')
        self.assertEqual(f'{value!s}', value)
        self.assertEqual(f'{value!r}', "'中文😀'")
        self.assertEqual(f'{value!a}', "'\\u4e2d\\u6587\\U0001f600'")
        self.assertEqual(f'{value:>5}', '  中文😀')

    def test_adjacent_literals(self):
        value = 3
        self.assertEqual('start ' f'{value}' u' end' F' {value + 1}', 'start 3 end 4')
        self.assertEqual(f'no fields' ' either', 'no fields either')
        self.assertEqual(f'{{' f'{value}' f'}}', '{3}')
        self.assertEqual((f'{value}'
                          f'{value + 1}'), '34')
        self.assertEqual('中文' f'{value}', '中文3')

    def test_adjacent_raw_literals(self):
        self.assertEqual(r'\u4e2d' f'{1}', '\\u4e2d1')
        self.assertEqual(f'{1}' r'\N{SNOWMAN}', '1\\N{SNOWMAN}')
        self.assertEqual(r'中文\n' f'{1}', '中文\\n1')

    def test_without_future_unicode_literals(self):
        source = u'''f"中文: {u'值'}"'''
        result = eval(compile(source, '<fstring>', 'eval', 0, True))
        self.assertEqual(result, u'中文: 值')
        self.assertEqual(type(result), type(u''))

    def test_format_spec_braces(self):
        class Echo(object):
            def __format__(self, spec):
                return spec
        value = Echo()
        self.assertEqual(f'{value:{{}}}', '{}')
        self.assertEqual(f'{value:{{1: 2}}}', '{1: 2}')
        self.assertEqual(f'{value:}}}', '}')
        self.assertEqual(f'{value:\N{SNOWMAN}}', '\N{SNOWMAN}')

    def test_multiline(self):
        value = 3
        self.assertEqual(f'''first
{value}
last''', 'first\n3\nlast')
        self.assertEqual(f'''{value +
                             2}''', '5')

    def test_expressions(self):
        data = {'name': 'Python'}
        self.assertEqual(f"{data['name'].upper()}", 'PYTHON')
        self.assertEqual(f'{[1, 2, 3][1:]}', '[2, 3]')
        self.assertEqual(f'{1, 2}', '(1, 2)')
        self.assertEqual(f'{[n * 2 for n in range(3)]}', '[0, 2, 4]')
        self.assertEqual(f'{sum(n * 2 for n in range(3))}', '6')
        self.assertEqual(f'{(lambda x: x + 1)(2)}', '3')
        self.assertEqual(f'{3 if True else 4}', '3')
        self.assertEqual(f"{ {'a': 2}['a'] }", '2')
        self.assertEqual(f"{'#'}", '#')
        self.assertEqual(f'{1 == 1} {1 != 2} {1 <= 2} {1 >= 2}', 'True True True False')

    def test_nested_fstring(self):
        value = 2
        self.assertEqual(f"outer {f'inner {value}'}", 'outer inner 2')
        self.assertEqual(f"{value:{f'0{3}d'}}", '002')

    def test_numeric_specs(self):
        value = 12.3456
        self.assertEqual(f'{value:.2f}', '12.35')
        self.assertEqual(f'{42:06d}', '000042')
        self.assertEqual(f'{255:#x}', '0xff')
        self.assertEqual(f'{1234567:,}', '1,234,567')
        self.assertEqual(f'{0.125:.1%}', '12.5%')
        self.assertEqual(f'{42:}', '42')

    def test_dynamic_specs(self):
        value, width, precision = 12.3456, 9, 2
        self.assertEqual(f'{value:{width}.{precision}f}', '    12.35')
        self.assertEqual(f'{42:{width}d}', '       42')
        self.assertEqual(f'{value:{width - 2}.{precision + 1}f}', ' 12.346')

    def test_string_specs(self):
        value = 'abc'
        self.assertEqual(f'{value:*^7}', '**abc**')
        self.assertEqual(f'{value!r:>8}', "   'abc'")
        self.assertEqual(f'{value!s:.2}', 'ab')

    def test_debug_fields(self):
        value = 'text'
        self.assertEqual(f'{value=}', "value='text'")
        self.assertEqual(f'{ value = }', " value = 'text'")
        self.assertEqual(f'{value=!s}', 'value=text')
        self.assertEqual(f'{value=:>6}', 'value=  text')
        self.assertEqual(f'{2 + 3=}', '2 + 3=5')
        self.assertEqual(f'{value = !r:>8}', "value =   'text'")

    def test_custom_protocol(self):
        class Value(object):
            def __format__(self, spec):
                return 'formatted:' + spec
            def __str__(self):
                return 'str'
            def __repr__(self):
                return 'repr'
        value = Value()
        self.assertEqual(f'{value}', 'formatted:')
        self.assertEqual(f'{value:test}', 'formatted:test')
        self.assertEqual(f'{value!s:>5}', '  str')
        self.assertEqual(f'{value!r}', 'repr')
        value.__format__ = lambda spec: 'wrong'
        self.assertEqual(f'{value}', 'formatted:')

    def test_custom_unicode_representations(self):
        class Value(object):
            def __repr__(self):
                return u'中文😀'
        value = Value()
        self.assertEqual(f'{value!r}', '中文😀')
        self.assertEqual(f'{value!a}', '\\u4e2d\\u6587\\U0001f600')
        class Text(type(u'')):
            def __repr__(self):
                return 'custom'
            def __str__(self):
                return 'override'
        value = Text('abc')
        self.assertEqual(f'{value!r}', 'custom')
        self.assertEqual(f'{value!s}', 'override')

    def test_unicode_repr_escaping(self):
        for value in (u"a'b", u'a"b', u'\n\r\t\\', u'\x00\x7f\xa0', u'中😀'):
            if not IS_JYTHON:
                self.assertEqual(f'{value!r}', repr(value))
            # Jython's standalone eval still has Python 2 str/unicode literal semantics.
            prefix = 'u' if IS_JYTHON else ''
            self.assertEqual(eval(prefix + f'{value!r}'), value)
        value = u'\x00\xa0'
        self.assertEqual(f'{value!a}', "'\\x00\\xa0'")

    def test_evaluation_order(self):
        events = []
        class Value(object):
            def __repr__(self):
                events.append('repr')
                return 'x'
            def __format__(self, spec):
                events.append('format:' + spec)
                return 'x'
        def get(label, result):
            events.append(label)
            return result
        value = Value()
        self.assertEqual(f"{get('value', value):{get('spec', '')}}{get('next', 2)}", 'x2')
        self.assertEqual(events, ['value', 'spec', 'format:', 'next'])
        del events[:]
        self.assertEqual(f"{get('value', value)!r:{get('spec', '>3')}}", '  x')
        self.assertEqual(events, ['value', 'spec', 'repr'])

    def test_not_global_helpers(self):
        def wrong(*args):
            raise AssertionError('a global helper was called')
        env = {'value': 12, 'format': wrong, 'str': wrong, 'repr': wrong,
               'ascii': wrong, 'eval': wrong}
        self.assertEqual(eval("f'{value!r}:{value!s}:{value!a}:{value}'", env), '12:12:12:12')

    def test_scope_and_closure(self):
        value, width = 3, 4
        def outer():
            def inner():
                return f'{value:0{width}d}'
            return inner
        inner = outer()
        self.assertEqual(inner(), '0003')
        self.assertIn('value', inner.__code__.co_freevars)
        self.assertIn('width', inner.__code__.co_freevars)
        value = 7
        self.assertEqual(inner(), '0007')

    def test_nonlocal(self):
        value = 1
        def change():
            nonlocal value
            value += 1
            return f'{value}'
        self.assertEqual(change(), '2')
        self.assertEqual(change(), '3')
        source = "def f():\n x = 1\n def g():\n  f'{x}'\n  nonlocal x\n"
        self.assertRaises(SyntaxError, compile, source, '<fstring>', 'exec')

    def test_class_and_defaults(self):
        class Value(object):
            value = 4
            label = f'{value}'
        self.assertEqual(Value.label, '4')
        value = 4
        def function(arg=f'{value}', *, text=f'{value + 1}'):
            return arg + text
        value = 9
        self.assertEqual(function(), '45')

    def test_generator_send(self):
        def generate():
            result = f"before {(yield 'value'):0{(yield 'width')}d} after"
            yield result
        gen = generate()
        self.assertEqual(next(gen), 'value')
        self.assertEqual(gen.send(7), 'width')
        self.assertEqual(gen.send(4), 'before 0007 after')
        self.assertRaises(StopIteration, next, gen)

    def test_generator_multiple_fields(self):
        def generate():
            yield f'{(yield 1)}:{(yield 2)}'
        gen = generate()
        self.assertEqual(next(gen), 1)
        self.assertEqual(gen.send('one'), 2)
        self.assertEqual(gen.send('two'), 'one:two')
        gen.close()

    def test_generator_throw(self):
        def generate():
            try:
                yield f'{(yield 1)}'
            except ValueError as error:
                yield f'caught:{error}'
        gen = generate()
        self.assertEqual(next(gen), 1)
        self.assertEqual(gen.throw(ValueError('bad')), 'caught:bad')
        gen.close()

    def test_runtime_errors(self):
        self.assertRaises(NameError, eval, "f'{missing}'", {})
        self.assertRaises(ZeroDivisionError, eval, "f'{1 / 0}'")
        self.assertRaises(ValueError, eval, "f'{3:invalid}'")
        self.assertRaises(TypeError, eval, "f'{object():x}'")
        class Bad(object):
            def __format__(self, spec):
                return 42
        self.assertRaises(TypeError, lambda: f'{Bad()}')

    def test_exception_short_circuit(self):
        events = []
        def bad():
            events.append('bad')
            raise ValueError('stop')
        def later():
            events.append('later')
            return 2
        self.assertRaises(ValueError, lambda: f'{bad()}{later()}')
        self.assertEqual(events, ['bad'])

    def test_not_docstring(self):
        def function():
            f'not a docstring'
        class Value(object):
            f'not a docstring either'
        self.assertIsNone(function.__doc__)
        self.assertIsNone(Value.__doc__)
        source = "f'not a docstring'\nfrom __future__ import division\n"
        self.assertRaises(SyntaxError, compile, source, '<fstring>', 'exec')

    def test_invalid_fields(self):
        sources = ["f'{}'", "f'{ }'", "f'{x'", "f'}'", "f'{x!}'",
                   "f'{x!q}'", "f'{x!ss}'", "f'{x!s '}", "f'{x:'",
                   "f'{(x]}'", "f'{x)}'", "f'{x:{y:{z}}}'",
                   "f'{lambda x: x}'", "f'{1 + }'", "f'{x=abc}'",
                   "f'{x # comment}'", r'''f"{'a\nb'}"''',
                   "bf'{x}'", "fb'{x}'", "uf'{x}'", "fu'{x}'",
                   "f'{x}' b'bytes'", "b'bytes' f'{x}'",
                   "f'{x}' = 1", "f'{x}' += 1", "del f'{x}'"]
        for source in sources:
            with self.assertRaises(SyntaxError, msg=source):
                compile(source, '<fstring>', 'exec')

    def test_ast_roundtrip(self):
        tree = ast.parse("f'hello {value!r:>{width}}'", mode='eval')
        self.assertIsInstance(tree.body, ast.JoinedStr)
        fields = [node for node in ast.walk(tree) if isinstance(node, ast.FormattedValue)]
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0].conversion, ord('r'))
        self.assertEqual(fields[1].conversion, -1)
        self.assertIsNone(fields[1].format_spec)
        self.assertEqual(eval(compile(tree, '<ast>', 'eval'), {'value': 'x', 'width': 5}), "hello   'x'")

    def test_ast_construction_and_transform(self):
        field = ast.FormattedValue(ast.Name(id='value', ctx=ast.Load()), -1, None)
        tree = ast.Expression(ast.JoinedStr([ast.Str(s=u'value='), field]))
        ast.fix_missing_locations(tree)
        self.assertEqual(eval(compile(tree, '<ast>', 'eval'), {'value': 8}), 'value=8')
        class Replace(ast.NodeTransformer):
            def visit_Name(self, node):
                return ast.copy_location(ast.Num(n=9), node)
        tree = Replace().visit(tree)
        self.assertEqual(eval(compile(tree, '<ast>', 'eval')), 'value=9')

    @unittest.skipUnless(IS_JYTHON, 'Jython AST validation and subtype regression')
    def test_ast_validation_and_subtypes(self):
        class Joined(ast.JoinedStr):
            pass
        class Field(ast.FormattedValue):
            pass
        field = Field(ast.Num(n=3), -1, None, lineno=2, col_offset=7)
        tree = ast.Expression(Joined([field]))
        ast.fix_missing_locations(tree)
        self.assertIs(type(field), Field)
        self.assertIs(type(tree.body), Joined)
        self.assertEqual(field.lineno, 2)
        self.assertEqual(field.col_offset, 7)
        self.assertEqual(eval(compile(tree, '<ast>', 'eval')), '3')
        field.conversion = ord('z')
        self.assertRaises(SyntaxError, compile, tree, '<ast>', 'eval')
        field.conversion = -1
        field.format_spec = ast.Num(n=2)
        self.assertRaises(SyntaxError, compile, tree, '<ast>', 'eval')
        tree.body.values = [ast.Num(n=3)]
        self.assertRaises(SyntaxError, compile, tree, '<ast>', 'eval')

    def test_locations(self):
        tree = ast.parse("\nresult = f'hello {value}'")
        names = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == 'value']
        self.assertEqual(names[0].lineno, 2)
        self.assertEqual(names[0].col_offset, 18)
        tree = ast.parse("result = f'''first\n{value}\nlast'''")
        names = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == 'value']
        self.assertEqual(names[0].lineno, 2)
        self.assertEqual(names[0].col_offset, 1)

    def test_lexical_errors(self):
        for source in ("f'abc", 'f"abc', "f'''hello\n{1}", 'rf"""hello\n{1}'):
            for mode in ('exec', 'eval', 'single'):
                with self.assertRaises(SyntaxError):
                    compile(source, '<fstring>', mode)
        try:
            compile("\nresult = f'{value!z}'", 'example.py', 'exec')
        except SyntaxError as error:
            self.assertEqual(error.filename, 'example.py')
            self.assertEqual(error.lineno, 2)
        else:
            self.fail('invalid conversion was accepted')

    def test_interactive(self):
        self.assertIsNotNone(codeop.compile_command("f'{1 + 2}'"))
        self.assertIsNone(codeop.compile_command("f'''hello\n{1}"))
        self.assertIsNotNone(codeop.compile_command("f'''hello\n{1}'''"))
        self.assertIsNone(codeop.compile_command("(f'{1}'\n"))
        self.assertRaises(SyntaxError, codeop.compile_command, "f'{}'")

    def test_datetime_example(self):
        now = datetime.now()
        self.assertEqual(f'原始 datetime 对象: {now}', u'原始 datetime 对象: ' + str(now))
        formatted = now.strftime('%Y-%m-%d %H:%M:%S')
        self.assertEqual(f'格式化后的时间: {formatted}', u'格式化后的时间: ' + formatted)
        parsed = datetime.strptime('2026-10-28 17:35:00', '%Y-%m-%d %H:%M:%S')
        self.assertEqual(f'解析字符串得到的时间: {parsed}', '解析字符串得到的时间: 2026-10-28 17:35:00')
        later = now + timedelta(days=3)
        earlier = now - timedelta(hours=2, minutes=30)
        self.assertEqual(f"3天后: {later.strftime('%Y-%m-%d')}", u'3天后: ' + later.strftime('%Y-%m-%d'))
        self.assertEqual(f"2小时30分钟前: {earlier.strftime('%H:%M:%S')}", u'2小时30分钟前: ' + earlier.strftime('%H:%M:%S'))
        days = datetime(2026, 12, 25) - now
        self.assertEqual(f'还有: {days.days} 天', u'还有: %d 天' % days.days)
        timestamp = time.time()
        result = datetime.fromtimestamp(timestamp)
        self.assertTrue(f'时间戳转回的时间: {result}'.startswith('时间戳转回的时间: '))
        self.assertEqual(f'{parsed:%Y-%m-%d %H:%M:%S}', '2026-10-28 17:35:00')


def test_main():
    from test import test_support
    test_support.run_unittest(FStringTest)


if __name__ == '__main__':
    unittest.main()
