"""Native JVM PEP 3132 and iterable-display unpacking regression tests.

The shared tests also run directly on CPython 3.15.2. This does not imply
that the native runtime implements the rest of the Python 3 object model.
"""
import ast
import codeop
import sys
import unittest


IS_JYTHON = sys.platform.startswith('java')


class UnpackingTests(unittest.TestCase):
    def test_assignment_positions(self):
        first, *rest = range(4)
        self.assertEqual((first, rest), (0, [1, 2, 3]))
        *rest, last = range(4)
        self.assertEqual((rest, last), ([0, 1, 2], 3))
        first, *rest, last = range(4)
        self.assertEqual((first, rest, last), (0, [1, 2], 3))
        *rest, = range(4)
        self.assertEqual(rest, [0, 1, 2, 3])
        self.assertIs(type(rest), list)

    def test_empty_captures(self):
        *rest, = []
        self.assertEqual(rest, [])
        first, *rest, last = [1, 2]
        self.assertEqual((first, rest, last), (1, [], 2))
        [*rest] = ()
        self.assertEqual(rest, [])

    def test_nested_targets(self):
        (a, *b), [c, *d, e] = [[1, 2, 3], [4, 5, 6, 7]]
        self.assertEqual((a, b, c, d, e), (1, [2, 3], 4, [5, 6], 7))
        a, *(b, c) = [1, 2, 3]
        self.assertEqual((a, b, c), (1, 2, 3))
        a, *[b, *c] = [1, 2, 3, 4]
        self.assertEqual((a, b, c), (1, 2, [3, 4]))
        a, *[] = [1]
        self.assertEqual(a, 1)

    def test_fresh_list_and_chain(self):
        source = [1, 2, 3]
        a, *b = c, *d = source
        self.assertEqual((a, b, c, d), (1, [2, 3], 1, [2, 3]))
        self.assertIsNot(b, d)
        self.assertIsNot(b, source)
        b.append(4)
        self.assertEqual(source, [1, 2, 3])
        self.assertEqual(d, [2, 3])

    def test_iterator_consumed_once(self):
        source = iter(range(5))
        a, *b, c = source
        self.assertEqual((a, b, c), (0, [1, 2, 3], 4))
        self.assertEqual(list(source), [])

    def test_not_enough_values(self):
        for source in ([], [1], iter([1])):
            with self.assertRaises(ValueError) as caught:
                a, *b, c = source
            self.assertIn('expected at least 2', str(caught.exception))
        a, b, c = 10, 20, 30
        try:
            a, *b, c = [1]
        except ValueError:
            pass
        self.assertEqual((a, b, c), (10, 20, 30))

    def test_non_iterable(self):
        with self.assertRaises(TypeError):
            *rest, = 42
        for source in ('[*42]', '(*42,)', '{*42}'):
            with self.assertRaises(TypeError):
                eval(source)

    def test_iteration_failure_before_stores(self):
        def broken():
            yield 1
            raise RuntimeError('iterator failed')
        a, b = 10, 20
        with self.assertRaises(RuntimeError):
            a, *b = broken()
        self.assertEqual((a, b), (10, 20))

    def test_partial_nested_assignment(self):
        a, b, c = 10, 20, 30
        with self.assertRaises(ValueError):
            a, *(b, c) = [1, 2]
        self.assertEqual((a, b, c), (1, 20, 30))

    def test_attributes_subscripts_and_order(self):
        class Box(object):
            pass
        box = Box()
        target = [None]
        a, *box.value, target[0] = [1, 2, 3, 4]
        self.assertEqual((a, box.value, target), (1, [2, 3], [4]))
        data = [None, None]
        index, *data[index] = [1, 2, 3]
        self.assertEqual(data, [None, [2, 3]])

    def test_for_targets(self):
        result = []
        for first, *rest in [[1, 2, 3], [4]]:
            result.append((first, rest))
        self.assertEqual(result, [(1, [2, 3]), (4, [])])

    def test_comprehension_targets(self):
        rows = [[1, 2, 3], [4, 5]]
        self.assertEqual([(a, b) for a, *b in rows], [(1, [2, 3]), (4, [5])])
        self.assertEqual(list((a, b) for a, *b in rows), [(1, [2, 3]), (4, [5])])
        self.assertEqual({a for a, *b in rows}, {1, 4})
        self.assertEqual({a: b for a, *b in rows}, {1: [2, 3], 4: [5]})

    def test_with_target(self):
        events = []
        class Manager(object):
            def __enter__(self):
                return [1, 2, 3]
            def __exit__(self, *args):
                events.append('exit')
        with Manager() as (a, *b):
            self.assertEqual((a, b), (1, [2, 3]))
        self.assertEqual(events, ['exit'])

    def test_list_displays(self):
        self.assertEqual([*range(3)], [0, 1, 2])
        self.assertEqual([0, *[1, 2], 3, *iter([4]), *[]], [0, 1, 2, 3, 4])
        self.assertEqual([*[]], [])
        self.assertEqual([*[1, *[2, 3]]], [1, 2, 3])

    def test_tuple_displays(self):
        self.assertEqual((*range(3),), (0, 1, 2))
        self.assertEqual((0, *[1, 2], 3, *iter([4]), *[]), (0, 1, 2, 3, 4))
        self.assertEqual((*[],), ())
        result = 0, *[1, 2], 3
        self.assertEqual(result, (0, 1, 2, 3))

    def test_set_displays(self):
        self.assertEqual({*range(3)}, {0, 1, 2})
        self.assertEqual({0, *[1, 2, 1], 3, *iter([4]), *[]}, {0, 1, 2, 3, 4})
        self.assertEqual({*[]}, set())

    def test_display_evaluation_order(self):
        for template in ('[mark(0), *items(), mark(3)]',
                         '(mark(0), *items(), mark(3))',
                         '{mark(0), *items(), mark(3)}'):
            events = []
            def mark(value):
                events.append(value)
                return value
            def items():
                yield mark(1)
                yield mark(2)
            result = eval(template)
            self.assertEqual(events, [0, 1, 2, 3])
            self.assertEqual(sorted(result), [0, 1, 2, 3])

    def test_display_failure_stops_evaluation(self):
        for template in ('[*items(), mark()]', '(*items(), mark())', '{*items(), mark()}'):
            events = []
            def items():
                yield 1
                raise RuntimeError('stop')
            def mark():
                events.append('unexpected')
            with self.assertRaises(RuntimeError):
                eval(template)
            self.assertEqual(events, [])

    def test_set_hash_failure_stops_iteration(self):
        events = []
        def items():
            events.append('first')
            yield []
            events.append('unexpected')
            yield 1
        with self.assertRaises(TypeError):
            result = {*items()}
        self.assertEqual(events, ['first'])

    def test_builtins_can_be_shadowed(self):
        namespace = dict(list=None, tuple=None, set=None)
        eval(compile('a = [*[1, 2]]\nb = (*a,)\nc = {*a}\nx, *y = a',
                     '<shadowed>', 'exec'), namespace)
        self.assertEqual(namespace['a'], [1, 2])
        self.assertEqual(namespace['b'], (1, 2))
        self.assertEqual(namespace['c'], {1, 2})
        self.assertEqual(namespace['y'], [2])

    def test_closure_and_nonlocal(self):
        def outer():
            rest = None
            def assign():
                nonlocal rest
                first, *rest = range(4)
                return [first, *rest]
            def get():
                return rest
            return assign, get
        assign, get = outer()
        self.assertEqual(assign(), [0, 1, 2, 3])
        self.assertEqual(get(), [1, 2, 3])

    def test_class_globals_defaults(self):
        namespace = {}
        eval(compile('def f():\n global rest\n first, *rest = [1, 2, 3]\n'
                     'f()\nclass C:\n first, *tail = [4, 5, 6]\n'
                     'def g(x=[*rest]):\n return (*x,)\n', '<scope>', 'exec'), namespace)
        self.assertEqual(namespace['rest'], [2, 3])
        self.assertEqual(namespace['C'].tail, [5, 6])
        self.assertEqual(namespace['g'](), (2, 3))

    def test_generator_display_locals(self):
        for expression, expected in (('[0, *(yield 1), (yield 2), *[4]]', [0, 10, 11, 3, 4]),
                                     ('(0, *(yield 1), (yield 2), *[4])', (0, 10, 11, 3, 4)),
                                     ('{0, *(yield 1), (yield 2), *[4]}', {0, 10, 11, 3, 4})):
            namespace = {}
            eval(compile('def g():\n result = ' + expression + '\n yield result\n',
                         '<generator-display>', 'exec'), namespace)
            iterator = namespace['g']()
            self.assertEqual(next(iterator), 1)
            self.assertEqual(iterator.send([10, 11]), 2)
            self.assertEqual(iterator.send(3), expected)
            with self.assertRaises(StopIteration):
                next(iterator)

    def test_generator_assignment_and_target_yield(self):
        def gen():
            a, *b = (yield 'source')
            yield a, b
            target = [None]
            a, *target[(yield 'index')] = [4, 5, 6]
            yield a, target
        iterator = gen()
        self.assertEqual(next(iterator), 'source')
        self.assertEqual(iterator.send([1, 2, 3]), (1, [2, 3]))
        self.assertEqual(next(iterator), 'index')
        self.assertEqual(iterator.send(0), (4, [[5, 6]]))

    def test_generator_close_and_throw(self):
        events = []
        def gen():
            try:
                result = [1, *(yield 'pause'), 3]
                yield result
            finally:
                events.append('closed')
        iterator = gen()
        self.assertEqual(next(iterator), 'pause')
        iterator.close()
        self.assertEqual(events, ['closed'])
        iterator = gen()
        next(iterator)
        with self.assertRaises(RuntimeError):
            iterator.throw(RuntimeError('stop'))
        self.assertEqual(events, ['closed', 'closed'])

    def test_sequence_protocol(self):
        class Sequence(object):
            def __getitem__(self, index):
                if index >= 3:
                    raise IndexError(index)
                return index + 1
        a, *b = Sequence()
        self.assertEqual((a, b), (1, [2, 3]))
        self.assertEqual([*Sequence()], [1, 2, 3])

    def test_custom_iterator_protocol(self):
        class Iterator(object):
            def __init__(self):
                self.index = 0
            def __iter__(self):
                return self
            def __next__(self):
                self.index += 1
                if self.index > 3:
                    raise StopIteration
                return self.index
            next = __next__
        a, *b = Iterator()
        self.assertEqual((a, b), (1, [2, 3]))
        self.assertEqual([*Iterator()], [1, 2, 3])

    def test_assignment_combinations(self):
        for before in range(4):
            for after in range(4):
                names = ['p%d' % i for i in range(before)] + ['*middle']
                names += ['s%d' % i for i in range(after)]
                code = compile(', '.join(names) + ', = source', '<combinations>', 'exec')
                for length in range(9):
                    values = list(range(length))
                    namespace = {'source': iter(values)}
                    if length < before + after:
                        with self.assertRaises(ValueError):
                            eval(code, namespace)
                    else:
                        eval(code, namespace)
                        split = length - after
                        self.assertEqual(namespace['middle'], values[before:split])
                        self.assertEqual([namespace['p%d' % i] for i in range(before)],
                                         values[:before])
                        self.assertEqual([namespace['s%d' % i] for i in range(after)],
                                         values[split:])

    def test_generator_attribute_target(self):
        class Box(object):
            pass
        def gen():
            a, *(yield 'receiver').value, z = [1, 2, 3, 4]
            yield a, z
        box = Box()
        iterator = gen()
        self.assertEqual(next(iterator), 'receiver')
        self.assertEqual(iterator.send(box), (1, 4))
        self.assertEqual(box.value, [2, 3])

    def test_unpacking_in_fstring_and_conditional(self):
        values = [1, 2]
        self.assertEqual(f'{[*values, 3]}', '[1, 2, 3]')
        self.assertEqual([*(values if True else [])], [1, 2])
        self.assertEqual((lambda: (*values,))(), (1, 2))
        def f():
            return *values, 3
        self.assertEqual(f(), (1, 2, 3))

    def test_iter_method_error_propagates(self):
        class Broken(object):
            def __iter__(self):
                raise RuntimeError('iter failed')
        with self.assertRaises(RuntimeError):
            a, *b = Broken()
        with self.assertRaises(RuntimeError):
            result = [*Broken()]

    def test_plain_unpack_keeps_tuple_intact(self):
        source = (object(), object())
        original = source[:]
        a, b = source
        self.assertEqual(source, original)
        self.assertIs(a, source[0])
        self.assertIs(b, source[1])

    def test_invalid_syntax(self):
        for source in ('*x = [1]', 'a, *b, *c = [1, 2]', '*x', 'x = *y',
                       'del [a, *b]', '*x += [1]', '[a, *b] += [1]',
                       'a, *f() = [1, 2]', 'a, *1 = [1, 2]',
                       'for a, *b, *c in []:\n pass', 'if False:\n *x = []'):
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid-star>', 'exec')

    def test_interactive_input(self):
        self.assertIsNone(codeop.compile_command('a, *b = ['))
        self.assertIsNone(codeop.compile_command('values = [*[1, 2],'))
        self.assertIsNotNone(codeop.compile_command('a, *b = [1, 2]'))
        self.assertIsNotNone(codeop.compile_command('values = (*[1, 2],)'))

    def test_ast_roundtrip(self):
        tree = ast.parse('a, *b = [1, *[2, 3]]')
        stars = [node for node in ast.walk(tree) if isinstance(node, ast.Starred)]
        self.assertEqual(len(stars), 2)
        self.assertTrue(any(isinstance(node.ctx, ast.Store) for node in stars))
        self.assertTrue(any(isinstance(node.ctx, ast.Load) for node in stars))
        namespace = {}
        eval(compile(tree, '<star-ast>', 'exec'), namespace)
        self.assertEqual((namespace['a'], namespace['b']), (1, [2, 3]))


@unittest.skipUnless(IS_JYTHON, 'native JVM AST and Java integration')
class NativeUnpackingTests(unittest.TestCase):
    def test_java_collections_and_array(self):
        from java.util import ArrayList, Arrays
        from jarray import array
        values = ArrayList()
        for value in range(4):
            values.add(value)
        for source in (values, Arrays.asList(array([1, 2, 3], 'i')), array([0, 1, 2, 3], 'i')):
            expected = list(source)
            a, *b = source
            self.assertEqual((a, b), (expected[0], expected[1:]))
            self.assertEqual([*source], expected)
            self.assertEqual((*source,), tuple(expected))

    def test_ast_constructor_subclass_and_locations(self):
        class MyStar(ast.Starred):
            pass
        star = MyStar(ast.List(elts=[ast.Num(n=2)], ctx=ast.Load()), ast.Load(),
                      lineno=7, col_offset=3)
        self.assertEqual((star.lineno, star.col_offset), (7, 3))
        star.tag = 'custom'
        tree = ast.Expression(body=ast.List(elts=[star], ctx=ast.Load()))
        self.assertEqual(eval(compile(ast.fix_missing_locations(tree), '<ast-subclass>', 'eval')), [2])
        self.assertEqual(star.tag, 'custom')

    def test_ast_rejects_invalid_stars(self):
        for source in ('[*[1]]', 'a, *b = [1, 2]'):
            tree = ast.parse(source)
            star = next(node for node in ast.walk(tree) if isinstance(node, ast.Starred))
            star.ctx = ast.Del()
            with self.assertRaises(SyntaxError):
                compile(tree, '<invalid-context>', 'exec')
        tree = ast.Expression(body=ast.Starred(value=ast.Num(n=1), ctx=ast.Load()))
        with self.assertRaises(SyntaxError):
            compile(ast.fix_missing_locations(tree), '<bare-star>', 'eval')
        tree = ast.parse('a, *b = [1, 2]')
        star = next(node for node in ast.walk(tree) if isinstance(node, ast.Starred))
        star.value = ast.Num(n=1)
        with self.assertRaises(SyntaxError):
            compile(tree, '<invalid-target>', 'exec')

    def test_ast_rejects_wrong_value_context(self):
        for value in (ast.Name(id='x', ctx=ast.Store()),
                      ast.List(elts=[], ctx=ast.Store()), None):
            star = ast.Starred(value=value, ctx=ast.Load())
            tree = ast.Expression(body=ast.List(elts=[star], ctx=ast.Load()))
            with self.assertRaises(SyntaxError):
                compile(ast.fix_missing_locations(tree), '<value-context>', 'eval')

    def test_ast_rejects_nested_literal_target(self):
        tree = ast.parse('a, *[b] = [1, 2]')
        star = next(node for node in ast.walk(tree) if isinstance(node, ast.Starred))
        star.value.elts = [ast.Num(n=3)]
        with self.assertRaises(SyntaxError):
            compile(ast.fix_missing_locations(tree), '<nested-target>', 'exec')

    def test_ast_rejects_multiple_and_unreachable_stars(self):
        tree = ast.parse('if False:\n a, *b = [1, 2]')
        target = tree.body[0].body[0].targets[0]
        target.elts = list(target.elts) + [ast.Starred(ast.Name(id='c', ctx=ast.Store()),
                                                    ast.Store())]
        with self.assertRaises(SyntaxError):
            compile(ast.fix_missing_locations(tree), '<multiple-star>', 'exec')

    def test_unpacking_boundaries(self):
        class Base(object):
            pass
        namespace = {'bases': [Base]}
        eval(compile('class C(*bases):\n pass', '<class-unpacking>', 'exec'), namespace)
        self.assertEqual(namespace['C'].__bases__, (Base,))
        self.assertIsInstance(namespace['C'](), Base)
        for source in ('[*x for x in []]', '(*x for x in [])', '{*x for x in []}',
                       '{*x: 1}', 'class C(**mapping):\n pass'):
            with self.assertRaises(SyntaxError):
                compile(source, '<unsupported-unpacking>', 'exec')


def test_main():
    suite = unittest.TestSuite()
    for case in (UnpackingTests, NativeUnpackingTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError('native unpacking regression failed')


if __name__ == '__main__':
    unittest.main()