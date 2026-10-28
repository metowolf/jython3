"""Native JVM mapping displays, with shared CPython 3.15.2 comparisons.

This tests ** display semantics, not migration of the ordered dict object model.
"""
import ast
import codeop
import sys
import unittest


IS_JYTHON = sys.platform.startswith('java')


class MappingUnpackingTests(unittest.TestCase):
    def test_empty_and_fresh(self):
        source = {'a': []}
        result = {**source}
        self.assertIs(type(result), dict)
        self.assertIsNot(result, source)
        self.assertIs(result['a'], source['a'])
        result['b'] = 2
        self.assertNotIn('b', source)
        self.assertEqual({**{}, **{},}, {})

    def test_mixed_entries_and_overrides(self):
        self.assertEqual({**{'a': 1}, 'b': 2, **{'a': 3}, 'a': 4}, {'a': 4, 'b': 2})
        self.assertEqual({'a': 0, 'b': 2, **{'a': 3}, 'b': 4, **{'c': 5}},
                         {'a': 3, 'b': 4, 'c': 5})
        self.assertEqual({**{}, 'a': 1, 'a': 2, **{}, 'a': 3}, {'a': 3})

    def test_non_string_keys_and_none_values(self):
        source = {1: 'one', None: 'none', (2, 3): None}
        self.assertEqual({**source, False: 'false'},
                         {1: 'one', None: 'none', (2, 3): None, False: 'false'})
        self.assertEqual({None: 1, **{}, None: 2}, {None: 2})

    def test_nested_displays(self):
        self.assertEqual({**{**{'a': 1}}, 'b': {**{'c': 2}}}, {'a': 1, 'b': {'c': 2}})
        self.assertEqual([{**{'a': 1}}, *[{**{'b': 2}}]], [{'a': 1}, {'b': 2}])

    def test_operand_expressions(self):
        source = {'a': 1}
        self.assertEqual({**(source if True else {})}, source)
        self.assertEqual({**(lambda: source)()}, source)
        self.assertEqual({**[source][0], **dict(b=2)}, {'a': 1, 'b': 2})

    def test_mapping_protocol(self):
        events = []
        class Mapping(object):
            def keys(self):
                events.append('keys')
                return ('a', 'b')
            def __getitem__(self, key):
                events.append(key)
                return key.upper()
            def __iter__(self):
                raise AssertionError('must use keys, not mapping iteration')
        self.assertEqual({**Mapping()}, {'a': 'A', 'b': 'B'})
        self.assertEqual(events, ['keys', 'a', 'b'])

    def test_key_iterator_exhausted_before_getitem(self):
        events = []
        class Mapping(object):
            def keys(self):
                events.append('first')
                yield 'a'
                events.append('second')
                yield 'b'
                events.append('done')
            def __getitem__(self, key):
                events.append('get-' + key)
                return key
        self.assertEqual({**Mapping()}, {'a': 'a', 'b': 'b'})
        self.assertEqual(events, ['first', 'second', 'done', 'get-a', 'get-b'])

    def test_live_exact_key_list(self):
        keys = ['a']
        class Mapping(object):
            def keys(self):
                return keys
            def __getitem__(self, key):
                if key == 'a':
                    keys.append('b')
                return key
        self.assertEqual({**Mapping()}, {'a': 'a', 'b': 'b'})

    def test_duplicate_protocol_keys(self):
        events = []
        class Mapping(object):
            def keys(self):
                return ['x', 'x']
            def __getitem__(self, key):
                events.append(key)
                return len(events)
        self.assertEqual({**Mapping()}, {'x': 2})
        self.assertEqual(events, ['x', 'x'])

    def test_dict_subclass_fast_path(self):
        class Mapping(dict):
            def keys(self):
                raise AssertionError('dict fast path must bypass keys override')
            def __getitem__(self, key):
                raise AssertionError('dict fast path must bypass getitem override')
        self.assertEqual({**Mapping(a=1)}, {'a': 1})

    def test_dict_subclass_custom_iteration(self):
        events = []
        class Mapping(dict):
            def __iter__(self):
                raise AssertionError('keys must be used on generic mapping path')
            def keys(self):
                events.append('keys')
                return ['x']
            def __getitem__(self, key):
                events.append(key)
                return 99
        self.assertEqual({**Mapping(a=1)}, {'x': 99})
        self.assertEqual(events, ['keys', 'x'])

    def test_evaluation_order(self):
        events = []
        class Mapping(object):
            def keys(self):
                events.append('keys')
                return ['a']
            def __getitem__(self, key):
                events.append('get')
                return 1
        def mark(label, value):
            events.append(label)
            return value
        result = {mark('key0', 'x'): mark('value0', 0),
                  **mark('mapping', Mapping()),
                  mark('key1', 'b'): mark('value1', 2),
                  mark('key2', 'c'): mark('value2', 3), **mark('tail', {'a': 4})}
        self.assertEqual(result, {'x': 0, 'a': 4, 'b': 2, 'c': 3})
        self.assertEqual(events, ['key0', 'value0', 'mapping', 'keys', 'get',
                                  'key1', 'value1', 'key2', 'value2', 'tail'])

    def test_literal_group_evaluated_before_hashing(self):
        events = []
        class BadKey(object):
            def __hash__(self):
                events.append('hash')
                raise RuntimeError('bad hash')
        def mark(label, value):
            events.append(label)
            return value
        with self.assertRaises(RuntimeError):
            result = {**{}, mark('key1', BadKey()): mark('value1', 1),
                      mark('key2', 'b'): mark('value2', 2), **mark('unexpected', {})}
        self.assertEqual(events, ['key1', 'value1', 'key2', 'value2', 'hash'])

    def test_merge_before_next_expression(self):
        source = {'a': 1}
        def mutate():
            source['a'] = 2
            return source
        self.assertEqual({**source, 'snapshot': source['a'], **mutate()},
                         {'a': 2, 'snapshot': 1})

    def test_not_a_mapping(self):
        for value in (None, 1, [], [('a', 1)], iter([('a', 1)]), 'abc'):
            with self.assertRaises(TypeError) as caught:
                result = {**value}
            self.assertIn('not a mapping', str(caught.exception))

    def test_keys_must_be_callable_and_iterable(self):
        class NonCallable(object):
            keys = 1
        class NonIterable(object):
            def keys(self):
                return 1
        for value in (NonCallable(), NonIterable()):
            with self.assertRaises(TypeError):
                result = {**value}

    def test_keys_attribute_errors(self):
        class Broken(object):
            @property
            def keys(self):
                raise RuntimeError('attribute failed')
        with self.assertRaises(RuntimeError):
            result = {**Broken()}
        class Missing(object):
            @property
            def keys(self):
                raise AttributeError('missing')
        with self.assertRaises(TypeError):
            result = {**Missing()}

    def test_keys_call_error_preserved(self):
        class Broken(object):
            def keys(self):
                raise AttributeError('inside keys')
        with self.assertRaises(AttributeError) as caught:
            result = {**Broken()}
        self.assertEqual(str(caught.exception), 'inside keys')

    def test_keys_iteration_error_before_getitem(self):
        events = []
        class Broken(object):
            def keys(self):
                yield 'a'
                raise RuntimeError('keys iterator failed')
            def __getitem__(self, key):
                events.append(key)
                return 1
        with self.assertRaises(RuntimeError):
            result = {**Broken()}
        self.assertEqual(events, [])

    def test_getitem_failure_stops_next_mapping(self):
        events = []
        class Broken(object):
            def keys(self):
                return ['a', 'b']
            def __getitem__(self, key):
                events.append(key)
                raise KeyError('missing')
        def unexpected():
            events.append('unexpected')
            return {}
        result = 'unchanged'
        with self.assertRaises(KeyError):
            result = {**Broken(), **unexpected()}
        self.assertEqual(result, 'unchanged')
        self.assertEqual(events, ['a'])

    def test_unhashable_mapping_key(self):
        events = []
        class Broken(object):
            def keys(self):
                return [[], 'later']
            def __getitem__(self, key):
                events.append(key)
                return 1
        with self.assertRaises(TypeError):
            result = {**Broken()}
        self.assertEqual(events, [[]])

    def test_scope_closure_and_nonlocal(self):
        def outer():
            data = {'a': 1}
            def update():
                nonlocal data
                data = {**data, 'b': 2}
                return data
            return update
        self.assertEqual(outer()(), {'a': 1, 'b': 2})
        namespace = {'data': {'x': 3}}
        eval(compile('def f():\n global data\n data = {**data, "y": 4}\n'
                     'f()\nclass C:\n values = {**data}\n'
                     'def g(x={**data}):\n return x\n', '<mapping-scope>', 'exec'), namespace)
        self.assertEqual(namespace['C'].values, {'x': 3, 'y': 4})
        self.assertEqual(namespace['g'](), namespace['data'])

    def test_comprehension_and_lambda_values(self):
        self.assertEqual([{**{'a': x}} for x in range(3)], [{'a': 0}, {'a': 1}, {'a': 2}])
        self.assertEqual(list({**{'a': x}} for x in range(2)), [{'a': 0}, {'a': 1}])
        self.assertEqual({x: {**{'a': x}} for x in range(2)}, {0: {'a': 0}, 1: {'a': 1}})
        self.assertEqual((lambda d: {**d})({'a': 1}), {'a': 1})

    def test_generator_keys_values_and_mappings(self):
        def gen():
            result = {'initial': 0, **(yield 'mapping'),
                      (yield 'key1'): (yield 'value1'),
                      (yield 'key2'): (yield 'value2'), **(yield 'tail')}
            yield result
        iterator = gen()
        self.assertEqual(next(iterator), 'mapping')
        self.assertEqual(iterator.send({'a': 1}), 'key1')
        self.assertEqual(iterator.send('b'), 'value1')
        self.assertEqual(iterator.send(2), 'key2')
        self.assertEqual(iterator.send('c'), 'value2')
        self.assertEqual(iterator.send(3), 'tail')
        self.assertEqual(iterator.send({'a': 4}), {'initial': 0, 'a': 4, 'b': 2, 'c': 3})
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_generator_nested_display(self):
        def gen():
            result = [1, {**{'x': 1}, 'nested': {**(yield 'inner')},
                          **(yield 'outer')}, 3]
            yield result
        iterator = gen()
        self.assertEqual(next(iterator), 'inner')
        self.assertEqual(iterator.send({'y': 2}), 'outer')
        self.assertEqual(iterator.send({'x': 4}), [1, {'x': 4, 'nested': {'y': 2}}, 3])

    def test_generator_throw_and_close(self):
        events = []
        def gen():
            try:
                value = {**{'a': 1}, **(yield 'pause')}
                yield value
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

    def test_shadowed_builtins(self):
        namespace = {'dict': None, 'list': None, 'source': {'a': 1}}
        eval(compile('result = {**source, "b": 2}', '<shadow>', 'exec'), namespace)
        self.assertEqual(namespace['result'], {'a': 1, 'b': 2})

    def test_ast_roundtrip_and_null_key(self):
        tree = ast.parse('{**source, None: 2, "x": 3, **{}}', mode='eval')
        self.assertIsNone(tree.body.keys[0])
        self.assertIsNotNone(tree.body.keys[1])
        self.assertIsNone(tree.body.keys[-1])
        self.assertEqual(len(tree.body.values), 4)
        self.assertEqual(eval(compile(tree, '<mapping-ast>', 'eval'), {'source': {'a': 1}}),
                         {'a': 1, None: 2, 'x': 3})
        self.assertTrue(list(ast.walk(tree)))

    def test_manual_ast(self):
        tree = ast.Expression(body=ast.Dict(keys=[None], values=[ast.Name(id='d', ctx=ast.Load())]))
        self.assertEqual(eval(compile(ast.fix_missing_locations(tree), '<manual>', 'eval'),
                              {'d': {'a': 1}}), {'a': 1})

    def test_interactive_input(self):
        for source in ('d = {**', 'd = {**a,', 'd = {"a": 1, **'):
            self.assertIsNone(codeop.compile_command(source))
        for source in ('d = {**{}}', 'd = {"a": 1, **{}}', 'd = {**{}, "a": 1,}'):
            self.assertIsNotNone(codeop.compile_command(source))

    def test_invalid_syntax(self):
        for source in ('{**}', '{**a: 1}', '{**a, 1}', '{1, **a}', '{*a, **b}',
                       '{**a, *b}', '{"a": **b}', '[**a]', '(**a,)',
                       '{**a if True else b}', '{**lambda: a}', '{**a} = {}'):
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid-mapping>', 'exec')

    def test_invalid_display_targets(self):
        for source in ('{**a} += {}', 'del {**a}', 'x, {**a} = pair',
                       'for {**a} in []:\n pass', '[x for {**a} in []]',
                       '(x for {**a} in [])', '{x for {**a} in []}',
                       '{x: x for {**a} in []}', 'with manager as {**a}:\n pass',
                       'if False:\n {**a} = {}'):
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid-target>', 'exec')

    def test_display_subscript_is_valid_target(self):
        source = {'a': 1}
        {**source}['a'] = 2
        {**source}['a'] += 3
        del {**source}['a']
        self.assertEqual(source, {'a': 1})

    def test_many_entries_and_mappings(self):
        source = '{**{}, ' + ', '.join('%d: %d' % (i, i) for i in range(80)) + ', **{79: -1}}'
        expected = dict((i, i) for i in range(80))
        expected[79] = -1
        self.assertEqual(eval(source), expected)
        source = '{' + ', '.join('**{%d: %d}' % (i, i) for i in range(80)) + '}'
        self.assertEqual(eval(source), dict((i, i) for i in range(80)))


@unittest.skipUnless(IS_JYTHON, 'native AST and Java integration')
class NativeMappingUnpackingTests(unittest.TestCase):
    def test_java_maps(self):
        from java.util import HashMap, LinkedHashMap, Collections
        for mapping_type in (HashMap, LinkedHashMap):
            source = mapping_type()
            source.put('a', 1)
            source.put('b', 2)
            self.assertEqual({**source, 'a': 3}, {'a': 3, 'b': 2})
            self.assertEqual({**Collections.unmodifiableMap(source)}, {'a': 1, 'b': 2})
            self.assertEqual(source.get('a'), 1)

    def test_native_namespace_mapping(self):
        namespace = {'a': 1}
        eval(compile('snapshot = {**locals()}', '<namespace>', 'exec'), namespace)
        self.assertEqual(namespace['snapshot']['a'], 1)
        self.assertNotIn('snapshot', namespace['snapshot'])

    def test_reject_mismatched_ast_lists(self):
        for keys, values in (([None], []), ([], [ast.Num(n=1)])):
            tree = ast.Expression(body=ast.Dict(keys=keys, values=values))
            with self.assertRaises(SyntaxError):
                compile(ast.fix_missing_locations(tree), '<mismatched>', 'eval')

    def test_reject_missing_ast_value(self):
        for key in (None, ast.Num(n=1)):
            tree = ast.Expression(body=ast.Dict(keys=[key], values=[None]))
            with self.assertRaises(SyntaxError):
                compile(ast.fix_missing_locations(tree), '<missing>', 'eval')

    def test_reject_invalid_ast_contexts(self):
        for key, value in ((None, ast.Name(id='d', ctx=ast.Store())),
                           (ast.Name(id='k', ctx=ast.Del()), ast.Num(n=1)),
                           (None, ast.Starred(value=ast.Name(id='d', ctx=ast.Load()), ctx=ast.Load()))):
            tree = ast.Expression(body=ast.Dict(keys=[key], values=[value]))
            with self.assertRaises(SyntaxError):
                compile(ast.fix_missing_locations(tree), '<context>', 'eval')

    def test_unreachable_ast_still_validated(self):
        tree = ast.parse('if False:\n result = {**source}')
        tree.body[0].body[0].value.values = []
        with self.assertRaises(SyntaxError):
            compile(tree, '<unreachable>', 'exec')

    def test_manual_dict_targets_rejected(self):
        for source in ('target = 1', 'target += 1', 'del target',
                       'for target in []:\n pass', 'with manager as target:\n pass'):
            tree = ast.parse(source)
            statement = tree.body[0]
            target = ast.Dict(keys=[None], values=[ast.Name(id='d', ctx=ast.Load())])
            if hasattr(statement, 'targets'):
                statement.targets = [target]
            elif hasattr(statement, 'optional_vars'):
                statement.optional_vars = target
            else:
                statement.target = target
            with self.assertRaises(SyntaxError):
                compile(ast.fix_missing_locations(tree), '<manual-target>', 'exec')

    def test_unpacking_comprehension_not_enabled(self):
        with self.assertRaises(SyntaxError):
            compile('{**x for x in []}', '<unsupported>', 'eval')


def test_main():
    suite = unittest.TestSuite()
    for case in (MappingUnpackingTests, NativeMappingUnpackingTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError('native mapping unpacking regression failed')


if __name__ == '__main__':
    unittest.main()