"""Native generalized calls, with shared semantic checks on CPython 3.15.2."""
import ast
import codeop
import sys
import unittest

IS_JYTHON = sys.platform.startswith('java')


def collect(*args, **kwargs):
    return args, kwargs


class CallUnpackingTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(collect(*[], *(), **{}, **{},), ((), {}))
        self.assertEqual(collect(**{},), ((), {}))
        self.assertEqual(collect(*[],), ((), {}))

    def test_mixed_positional(self):
        self.assertEqual(collect(0, *[1, 2], 3, *(4,), 5), ((0, 1, 2, 3, 4, 5), {}))
        self.assertEqual(collect(*iter([1]), *[2], *'ab'), ((1, 2, 'a', 'b'), {}))

    def test_mixed_keywords(self):
        self.assertEqual(collect(a=1, **{'b': 2}, c=3, **{'d': 4}, e=5),
                         ((), {'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5}))
        self.assertEqual(collect(1, *[2], 3, x=4, *[5], **{'y': 6}),
                         ((1, 2, 3, 5), {'x': 4, 'y': 6}))

    def test_operand_expressions(self):
        self.assertEqual(collect(*[1] if True else [], **{'x': 2} if True else {}),
                         ((1,), {'x': 2}))
        self.assertEqual(collect(*(lambda: [1])(), **(lambda: {'a': 2})()),
                         ((1,), {'a': 2}))

    def test_duplicate_keywords(self):
        for source in ("collect(a=1, **{'a': 2})", "collect(**{'a': 1}, a=2)",
                       "collect(**{'a': 1}, **{'a': 2})"):
            with self.assertRaises(TypeError) as caught:
                eval(source)
            self.assertIn('multiple values', str(caught.exception))

    def test_positional_keyword_collision(self):
        def f(x):
            return x
        with self.assertRaises(TypeError):
            f(*[1], **{'x': 2})

    def test_modern_signature(self):
        def f(a, /, b, *rest, c, **kw):
            return a, b, rest, c, kw
        self.assertEqual(f(*[1], *[2, 3], **{'c': 4}, **{'a': 5}),
                         (1, 2, (3,), 4, {'a': 5}))

    def test_unicode_and_non_identifier_keys(self):
        source = {u'\u03bb': 1, 'not an identifier': 2, '': 3}
        self.assertEqual(collect(**{}, **source), ((), source))
        class String(str):
            pass
        self.assertEqual(collect(**{String('x'): 1}, **{}), ((), {'x': 1}))

    def test_non_string_keys(self):
        for key in (1, None, ('a',)):
            with self.assertRaises(TypeError) as caught:
                collect(**{key: 1}, **{})
            self.assertIn('keywords must be strings', str(caught.exception))

    def test_key_type_check_after_merges(self):
        events = []
        def later():
            events.append('later')
            return {}
        with self.assertRaises(TypeError):
            collect(**{1: 2}, **later())
        self.assertEqual(events, ['later'])

    def test_mapping_protocol_without_len(self):
        events = []
        class Mapping(object):
            def keys(self):
                events.append('keys')
                return iter(['a', 'b'])
            def __getitem__(self, key):
                events.append(key)
                return key.upper()
            def __iter__(self):
                raise AssertionError('mapping iteration must not be used')
        self.assertEqual(collect(**Mapping(), **{'c': 3}), ((), {'a': 'A', 'b': 'B', 'c': 3}))
        self.assertEqual(events, ['keys', 'a', 'b'])

    def test_key_iterator_consumed_before_values(self):
        events = []
        class Mapping(object):
            def keys(self):
                events.append('first')
                yield 'a'
                events.append('last')
            def __getitem__(self, key):
                events.append('get')
                return 1
        self.assertEqual(collect(**Mapping()), ((), {'a': 1}))
        self.assertEqual(events, ['first', 'last', 'get'])

    def test_key_iterator_error_before_values(self):
        events = []
        class Mapping(object):
            def keys(self):
                yield 'a'
                raise RuntimeError('keys failed')
            def __getitem__(self, key):
                events.append('unexpected')
        with self.assertRaises(RuntimeError):
            collect(**Mapping())
        self.assertEqual(events, [])

    def test_duplicate_before_getitem(self):
        events = []
        class Mapping(object):
            def keys(self):
                return ['x', 'x']
            def __getitem__(self, key):
                events.append(key)
                return 1
        with self.assertRaises(TypeError):
            collect(**Mapping())
        self.assertEqual(events, ['x'])
        events[:] = []
        with self.assertRaises(TypeError):
            collect(x=1, **Mapping())
        self.assertEqual(events, [])

    def test_unhashable_key_before_getitem(self):
        events = []
        class Mapping(object):
            def keys(self):
                return [[]]
            def __getitem__(self, key):
                events.append('unexpected')
        with self.assertRaises(TypeError):
            collect(**Mapping())
        self.assertEqual(events, [])

    def test_live_key_list(self):
        keys = ['a']
        class Mapping(object):
            def keys(self):
                return keys
            def __getitem__(self, key):
                if key == 'a':
                    keys.append('b')
                return key
        self.assertEqual(collect(**Mapping()), ((), {'a': 'a', 'b': 'b'}))

    def test_dict_subclass_dispatch(self):
        class Fast(dict):
            def keys(self):
                raise AssertionError('fast path')
            def __getitem__(self, key):
                raise AssertionError('fast path')
        self.assertEqual(collect(**Fast(a=1), **{}), ((), {'a': 1}))
        class Generic(Fast):
            def __iter__(self):
                raise AssertionError('use keys instead')
            def keys(self):
                return ['b']
            def __getitem__(self, key):
                return 2
        self.assertEqual(collect(**Generic(a=1), **{}), ((), {'b': 2}))

    def test_not_a_mapping(self):
        for value in (None, 1, [], [('a', 1)], 'abc'):
            with self.assertRaises(TypeError):
                collect(**{}, **value)

    def test_keys_errors_propagate(self):
        class Missing(object):
            @property
            def keys(self):
                raise AttributeError('missing')
        class Broken(object):
            def keys(self):
                raise AttributeError('inside keys')
        class NonCallable(object):
            keys = 1
        class NonIterable(object):
            def keys(self):
                return 1
        for mapping in (Missing(), NonCallable(), NonIterable()):
            with self.assertRaises(TypeError):
                collect(**mapping)
        with self.assertRaises(AttributeError) as caught:
            collect(**Broken())
        self.assertEqual(str(caught.exception), 'inside keys')

    def test_getitem_error_stops_later_mapping(self):
        events = []
        class Broken(object):
            def keys(self):
                return ['a']
            def __getitem__(self, key):
                raise KeyError(key)
        def later():
            events.append('unexpected')
            return {}
        with self.assertRaises(KeyError):
            collect(**Broken(), **later())
        self.assertEqual(events, [])

    def test_positional_before_keyword_expressions(self):
        events = []
        def mark(label, value):
            events.append(label)
            return value
        result = mark('function', collect)(a=mark('keyword1', 1),
                   *mark('star1', [2]), b=mark('keyword2', 3), *mark('star2', [4]))
        self.assertEqual(result, ((2, 4), {'a': 1, 'b': 3}))
        self.assertEqual(events, ['function', 'star1', 'star2', 'keyword1', 'keyword2'])

    def test_immediate_multi_star_consumption(self):
        events = []
        def items():
            events.append('consume')
            yield 1
        def mark(label, value):
            events.append(label)
            return value
        self.assertEqual(collect(*items(), mark('arg', 2), *mark('star', [3]),
                                 a=mark('keyword', 4)), ((1, 2, 3), {'a': 4}))
        self.assertEqual(events, ['consume', 'arg', 'star', 'keyword'])

    def test_single_star_consumption_after_keywords(self):
        events = []
        def items():
            events.append('consume')
            yield 1
        def mark(label, value):
            events.append(label)
            return value
        self.assertEqual(collect(*mark('star', items()), a=mark('keyword', 2),
                                 **mark('mapping', {'b': 3})), ((1,), {'a': 2, 'b': 3}))
        self.assertEqual(events, ['star', 'keyword', 'mapping', 'consume'])

    def test_keyword_group_before_duplicate_check(self):
        events = []
        def mark(label):
            events.append(label)
            return 1
        with self.assertRaises(TypeError):
            collect(**{'a': 0}, a=mark('a'), b=mark('b'), **mark('unexpected'))
        self.assertEqual(events, ['a', 'b'])

    def test_duplicate_stops_single_star_consumption(self):
        events = []
        def items():
            events.append('unexpected')
            yield 1
        with self.assertRaises(TypeError):
            collect(*items(), a=1, **{'a': 2})
        self.assertEqual(events, [])

    def test_iteration_failure_stops_later_args(self):
        events = []
        def items():
            yield 1
            raise RuntimeError('iterator failed')
        def later():
            events.append('unexpected')
            return []
        with self.assertRaises(RuntimeError):
            collect(*items(), *later())
        self.assertEqual(events, [])

    def test_iter_typeerror_preserved(self):
        class Broken(object):
            def __iter__(self):
                raise TypeError('inside iter')
        for source in ('collect(*Broken())', 'collect(*Broken(), *[])'):
            with self.assertRaises(TypeError) as caught:
                eval(source)
            self.assertEqual(str(caught.exception), 'inside iter')

    def test_reserved_names_via_mapping(self):
        mapping = {'True': 1, 'False': 2, 'None': 3, '__debug__': 4}
        self.assertEqual(collect(**mapping, **{}), ((), mapping))

    def test_sequence_and_iterator_protocol(self):
        class Sequence(object):
            def __getitem__(self, index):
                if index == 2:
                    raise IndexError(index)
                return index
        class Iterator(object):
            def __init__(self):
                self.i = 0
            def __iter__(self):
                return self
            def __next__(self):
                if self.i == 2:
                    raise StopIteration
                self.i += 1
                return self.i
            next = __next__
        self.assertEqual(collect(*Sequence(), *Iterator()), ((0, 1, 1, 2), {}))

    def test_non_iterable(self):
        for source in ('collect(*1)', 'collect(*1, *[])', 'collect(*[], *None)'):
            with self.assertRaises(TypeError):
                eval(source)

    def test_bound_method_and_callable(self):
        class Callable(object):
            def __call__(self, *args, **kwargs):
                return args, kwargs
            method = __call__
        obj = Callable()
        for function in (obj, obj.method):
            self.assertEqual(function(*[1], *[2], **{'a': 3}, b=4),
                             ((1, 2), {'a': 3, 'b': 4}))
        self.assertEqual(max(*[1], *[3, 2]), 3)

    def test_sources_not_mutated(self):
        marker = []
        source = [marker]
        mapping = {'a': marker}
        args, kw = collect(*source, *[], **mapping, **{})
        self.assertIs(args[0], marker)
        self.assertIs(kw['a'], marker)
        kw['b'] = 2
        self.assertEqual(source, [marker])
        self.assertEqual(mapping, {'a': marker})

    def test_shadowed_builtins(self):
        namespace = {'list': None, 'tuple': None, 'dict': None, 'collect': collect}
        eval(compile('result = collect(*[1], *[2], **{"a": 3}, **{"b": 4})',
                     '<shadow>', 'exec'), namespace)
        self.assertEqual(namespace['result'], ((1, 2), {'a': 3, 'b': 4}))

    def test_closure_comprehension_and_decorator(self):
        def outer():
            args = [1]
            def inner():
                return collect(*args, *[2], **{'a': 3})
            return inner
        self.assertEqual(outer()(), ((1, 2), {'a': 3}))
        self.assertEqual([collect(*[x], *[]) for x in range(2)], [((0,), {}), ((1,), {})])
        def decorate(*args, **kw):
            def apply(function):
                function.tag = args, kw
                return function
            return apply
        @decorate(*[1], *[2], **{'a': 3}, b=4)
        def f():
            pass
        self.assertEqual(f.tag, ((1, 2), {'a': 3, 'b': 4}))

    def test_generator_arguments(self):
        def gen():
            result = (yield 'function')((yield 'first'), *(yield 'star1'),
                       (yield 'last'), *(yield 'star2'), a=(yield 'a'),
                       b=(yield 'b'), **(yield 'mapping'), c=(yield 'c'))
            yield result
        iterator = gen()
        self.assertEqual(next(iterator), 'function')
        for value, label in ((collect, 'first'), (0, 'star1'), ([1], 'last'),
                             (2, 'star2'), ([3], 'a'), (4, 'b'), (5, 'mapping'),
                             ({'d': 6}, 'c')):
            self.assertEqual(iterator.send(value), label)
        self.assertEqual(iterator.send(7), ((0, 1, 2, 3), {'a': 4, 'b': 5, 'd': 6, 'c': 7}))
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_generator_single_star_and_nested_calls(self):
        def gen():
            yield [collect(*[1], *collect(*(yield 'args'), **(yield 'kw'))[0]), 9]
        iterator = gen()
        self.assertEqual(next(iterator), 'args')
        self.assertEqual(iterator.send([2, 3]), 'kw')
        self.assertEqual(iterator.send({'x': 4}), [((1, 2, 3), {}), 9])

    def test_generator_throw_close(self):
        events = []
        def gen():
            try:
                yield collect(*[1], *(yield 'pause'), **{'x': 2})
            finally:
                events.append('closed')
        iterator = gen()
        self.assertEqual(next(iterator), 'pause')
        iterator.close()
        iterator = gen()
        next(iterator)
        with self.assertRaises(RuntimeError):
            iterator.throw(RuntimeError('stop'))
        self.assertEqual(events, ['closed', 'closed'])

    def test_generator_expression_argument(self):
        self.assertEqual(tuple(x for x in range(3)), (0, 1, 2))
        self.assertEqual(collect(*(x for x in range(2)), *[2]), ((0, 1, 2), {}))

    def test_ast_roundtrip(self):
        tree = ast.parse('collect(0, *[1], *[2], a=3, **{"b": 4}, **{})', mode='eval')
        self.assertIsInstance(tree.body.args[1], ast.Starred)
        self.assertIsInstance(tree.body.args[1].ctx, ast.Load)
        self.assertIsNone(tree.body.keywords[1].arg)
        self.assertEqual(eval(compile(tree, '<call-ast>', 'eval')), ((0, 1, 2), {'a': 3, 'b': 4}))

    def test_interactive_input(self):
        for source in ('collect(*', 'collect(*a, *', 'collect(**a, **', 'collect(**a, b='):
            self.assertIsNone(codeop.compile_command(source))
        self.assertIsNotNone(codeop.compile_command('collect(*[], *[], **{}, **{},)'))

    def test_invalid_syntax(self):
        for source in ('collect(a=1, 2)', 'collect(**a, 2)', 'collect(**a, *b)',
                       'collect(a=1, **b, a=2)', 'collect(*a, b=1, 2)',
                       'collect(*a, x for x in [])', 'collect(x for x in [],)',
                       'collect(x for x in [], **{})', 'collect(**)', 'collect(*)',
                       'collect(1=2)', 'collect(a.b=2)', 'collect(None=2)',
                       'collect(True=1)', 'collect(False=1)', 'collect(__debug__=1)',
                       'if False:\n collect(**a, *b)'):
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid-call>', 'exec')

    def test_many_arguments(self):
        source = 'collect(' + ', '.join('*[%d]' % i for i in range(80)) + ', '
        source += ', '.join('**{"k%d": %d}' % (i, i) for i in range(80)) + ')'
        self.assertEqual(eval(source), (tuple(range(80)), dict(('k%d' % i, i) for i in range(80))))


@unittest.skipUnless(IS_JYTHON, 'native JVM AST and Java integration')
class NativeCallUnpackingTests(unittest.TestCase):
    def test_java_inputs(self):
        from java.util import ArrayList, LinkedHashMap
        from jarray import array
        values = ArrayList()
        values.add(1)
        mapping = LinkedHashMap()
        mapping.put('a', 3)
        self.assertEqual(collect(*values, *array([2], 'i'), **mapping, b=4),
                         ((1, 2), {'a': 3, 'b': 4}))

    def test_java_overloads(self):
        from java.lang import Math, StringBuilder
        self.assertEqual(Math.max(*[3], *[7]), 7)
        builder = StringBuilder(*[], *['ab'])
        builder.append(*[], *['cd'])
        self.assertEqual(str(builder), 'abcd')

    def test_native_namespace(self):
        namespace = {'x': 3, 'collect': collect}
        eval(compile('result = collect(**locals(), **{})', '<namespace>', 'exec'), namespace)
        self.assertEqual(namespace['result'][1]['x'], 3)

    def test_legacy_ast_fields(self):
        tree = ast.parse('collect(0, a=1)', mode='eval')
        tree.body.starargs = ast.List(elts=[ast.Num(n=2)], ctx=ast.Load())
        tree.body.kwargs = ast.Dict(keys=[ast.Str(s='b')], values=[ast.Num(n=3)])
        self.assertEqual(eval(compile(ast.fix_missing_locations(tree), '<legacy>', 'eval')),
                         ((0, 2), {'a': 1, 'b': 3}))

    def test_mixed_ast_fields_rejected(self):
        for field in ('starargs', 'kwargs'):
            tree = ast.parse('collect(*[], **{})', mode='eval')
            setattr(tree.body, field, ast.Name(id='source', ctx=ast.Load()))
            with self.assertRaises(SyntaxError):
                compile(ast.fix_missing_locations(tree), '<mixed>', 'eval')

    def test_invalid_ast_context_and_missing_values(self):
        for value in (None, ast.Name(id='source', ctx=ast.Store()),
                      ast.Starred(value=ast.Num(n=1), ctx=ast.Load())):
            for source in ('collect(*[])', 'collect(**{})'):
                tree = ast.parse(source, mode='eval')
                if tree.body.args:
                    tree.body.args[0].value = value
                else:
                    tree.body.keywords[0].value = value
                with self.assertRaises(SyntaxError):
                    compile(ast.fix_missing_locations(tree), '<bad-value>', 'eval')
        tree = ast.parse('collect(*[])', mode='eval')
        tree.body.args[0].ctx = ast.Store()
        with self.assertRaises(SyntaxError):
            compile(tree, '<bad-star-context>', 'eval')

    def test_unreachable_duplicate_ast(self):
        tree = ast.parse('if False:\n collect(a=1, **{})')
        call = tree.body[0].body[0].value
        call.keywords = list(call.keywords) + [ast.keyword(arg='a', value=ast.Num(n=2))]
        with self.assertRaises(SyntaxError):
            compile(ast.fix_missing_locations(tree), '<unreachable>', 'exec')


def test_main():
    suite = unittest.TestSuite()
    for case in (CallUnpackingTests, NativeCallUnpackingTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError('native call unpacking regression failed')


if __name__ == '__main__':
    unittest.main()
