"""Native assignment expressions, excluding legacy comprehension scopes."""
import ast
import codeop
import io
import sys
import tokenize
import unittest

IS_JYTHON = sys.platform.startswith('java')


def execute(source, namespace=None):
    if namespace is None:
        namespace = {'__name__': __name__}
    eval(compile(source, '<named-expr>', 'exec'), namespace)
    return namespace


class NamedExpressionTests(unittest.TestCase):
    def test_result_identity_and_binding(self):
        marker = object()
        self.assertIs((bound := marker), marker)
        self.assertIs(bound, marker)
        self.assertIs((bound := None), None)
        self.assertIs(bound, None)

    def test_rhs_once_and_nested_order(self):
        events = []
        def rhs():
            events.append('rhs')
            return object()
        self.assertIs((first := (second := rhs())), first)
        self.assertIs(first, second)
        self.assertEqual(events, ['rhs'])

    def test_rhs_failure_preserves_binding(self):
        bound = object()
        original = bound
        def fail():
            raise ValueError('marker')
        with self.assertRaises(ValueError):
            (bound := fail())
        self.assertIs(bound, original)

    def test_rhs_reads_old_value(self):
        value = 10
        self.assertEqual((value := value + 1), 11)
        self.assertEqual(value, 11)

    def test_short_circuit(self):
        value = 0
        self.assertFalse(False and (value := 1))
        self.assertTrue(True or (value := 2))
        self.assertEqual(value, 0)
        self.assertEqual(True and (value := 3), 3)
        self.assertEqual(value, 3)

    def test_if_elif_and_truth_protocol(self):
        events = []
        class Truth(object):
            def __bool__(self):
                events.append('truth')
                return True
            __nonzero__ = __bool__
        ns = execute('if first := 0:\n result = 1\nelif second := truth:\n result = 2\nelse:\n result = 3', {'truth': Truth()})
        self.assertEqual(ns['result'], 2)
        self.assertEqual(ns['first'], 0)
        self.assertIs(ns['second'], ns['truth'])
        self.assertEqual(events, ['truth'])

    def test_while_and_else(self):
        ns = execute('values = iter([1, 2, 0])\nseen = []\nwhile current := next(values):\n seen.append(current)\nelse:\n ended = current')
        self.assertEqual(ns['seen'], [1, 2])
        self.assertEqual(ns['ended'], 0)

    def test_precedence(self):
        self.assertIs((value := 1 < 2), True)
        self.assertIs(value, True)
        self.assertEqual((value := 0 or 3), 3)
        self.assertEqual((value := 4 if True else 5), 4)
        self.assertEqual((value := 1, 2), (1, 2))
        self.assertEqual(value, 1)
        self.assertEqual((value := (1, 2)), (1, 2))
        self.assertEqual(value, (1, 2))

    def test_displays_and_unpacking(self):
        self.assertEqual([a := 1, b := 2, *[3]], [1, 2, 3])
        self.assertEqual((a, b), (1, 2))
        self.assertEqual({c := 4, 5}, {4, 5})
        self.assertEqual(c, 4)
        self.assertEqual({(key := 'a'): (value := 6), **{'b': 7}}, {'a': 6, 'b': 7})
        self.assertEqual((key, value), ('a', 6))
        self.assertEqual([*(items := [8, 9])], [8, 9])
        self.assertEqual(items, [8, 9])

    def test_dictionary_and_set_grammar_boundaries(self):
        self.assertEqual({value := 1,}, {1})
        self.assertEqual({(key := 'x'): (value := 2),}, {'x': 2})
        self.assertEqual({n for n in [1, 2]}, {1, 2})
        self.assertEqual({n: n + 1 for n in [1, 2]}, {1: 2, 2: 3})
        for source in ('{n for n in [1],}', '{n: n for n in [1],}',
                       '{value := 1: 2}', '{1: value := 2}'):
            with self.assertRaises(SyntaxError):
                compile(source, '<dict-set-boundary>', 'eval')

    def test_calls_and_keywords(self):
        def collect(*args, **kwargs):
            return args, kwargs
        result = collect(a := 1, *(items := [2]), key=(b := 3), **(mapping := {'other': 4}))
        self.assertEqual(result, ((1, 2), {'key': 3, 'other': 4}))
        self.assertEqual((a, b, items, mapping), (1, 3, [2], {'other': 4}))

    def test_subscripts_and_slice_parentheses(self):
        values = [10, 20, 30, 40]
        self.assertEqual(values[index := 1], 20)
        self.assertEqual(index, 1)
        self.assertEqual(values[(lower := 1):(upper := 4):(step := 2)], [20, 40])
        self.assertEqual((lower, upper, step), (1, 4, 2))

    def test_assignment_target_temporaries(self):
        items = [0, 0]
        items[index := 0], other = [5, 6]
        self.assertEqual((items, index, other), ([5, 0], 0, 6))
        class Box(object):
            pass
        box = Box()
        (target := box).value = 7
        self.assertIs(target, box)
        self.assertEqual(box.value, 7)
        items[index := 0] += (increment := 2)
        self.assertEqual((items, index, increment), ([7, 0], 0, 2))

    def test_return_assert_and_for(self):
        def f():
            return (local := 12), local
        self.assertEqual(f(), (12, 12))
        assert (truth := True)
        self.assertTrue(truth)
        values = []
        for item in (source := [1, 2]):
            values.append(item)
        self.assertEqual(values, source)

    def test_global_binding(self):
        ns = execute('value = 1\ndef f():\n global value\n return (value := 42)\nresult = f()')
        self.assertEqual((ns['value'], ns['result']), (42, 42))

    def test_nonlocal_binding(self):
        def outer():
            value = 1
            def inner():
                nonlocal value
                return (value := 42)
            return inner(), value
        self.assertEqual(outer(), (42, 42))

    def test_closure_and_later_outer_binding(self):
        def outer():
            def read():
                return value
            (value := 42)
            return read
        self.assertEqual(outer()(), 42)
        ns = execute('def outer():\n def set_value():\n  nonlocal value\n  return (value := 7)\n value = 1\n set_value()\n return value\nresult = outer()')
        self.assertEqual(ns['result'], 7)

    def test_function_unbound_local(self):
        ns = execute('value = 99\ndef f():\n result = value\n (value := 1)\n return result')
        with self.assertRaises(UnboundLocalError):
            ns['f']()
        self.assertEqual(ns['value'], 99)

    def test_lambda_local_scope(self):
        value = 1
        function = lambda: (value := 2)
        self.assertEqual(function(), 2)
        self.assertEqual(value, 1)
        function = lambda: ((value := 3), lambda: value)
        result, read = function()
        self.assertEqual((result, read()), (3, 3))

    def test_default_evaluated_in_outer_scope(self):
        ns = execute('def f(arg=(default := 42)):\n return arg\nresult = f()')
        self.assertEqual((ns['default'], ns['result']), (42, 42))
        ns = execute('f = lambda arg=(default := 7): arg\nresult = f()')
        self.assertEqual((ns['default'], ns['result']), (7, 7))

    def test_class_namespace_and_private_name(self):
        class C(object):
            result = (__private := 42)
            pair = (__private, result)
        self.assertEqual(C._C__private, 42)
        self.assertEqual(C.pair, (42, 42))

    def test_class_base_outer_binding(self):
        ns = execute('class C(base := object): pass\n')
        self.assertIs(ns['base'], object)
        self.assertTrue(issubclass(ns['C'], ns['base']))

    def test_decorators_bind_before_defaults(self):
        events = []
        def factory(label):
            events.append(label)
            def apply(function):
                events.append('apply-' + label)
                return function
            return apply
        ns = execute('@first := factory("first")\n@second := factory("second")\ndef f(arg=(default := first)):\n return arg', {'factory': factory})
        self.assertEqual(events, ['first', 'second', 'apply-second', 'apply-first'])
        self.assertIs(ns['f'](), ns['first'])
        self.assertIs(ns['default'], ns['first'])

    def test_class_decorator_assignment(self):
        ns = execute('@deco := lambda cls: cls\nclass C(object): pass')
        self.assertIs(ns['deco'](ns['C']), ns['C'])

    def test_fstring_parentheses_and_format_boundary(self):
        self.assertEqual(f'{(value := 42)}', '42')
        self.assertEqual(value, 42)
        value = 7
        self.assertEqual(f'{value:=3}', '  7')
        self.assertEqual(value, 7)

    def test_with_context_expression(self):
        class Manager(object):
            def __enter__(self):
                return 42
            def __exit__(self, *args):
                return False
        with (manager := Manager()) as value:
            self.assertEqual(value, 42)
        self.assertIsInstance(manager, Manager)

    def test_generator_rhs_delayed_binding(self):
        def gen():
            value = 'old'
            yield value
            yield (value := (yield 'send'))
            yield value
        iterator = gen()
        self.assertEqual(next(iterator), 'old')
        self.assertEqual(next(iterator), 'send')
        marker = object()
        self.assertIs(iterator.send(marker), marker)
        self.assertIs(next(iterator), marker)
        iterator.close()

    def test_generator_rhs_throw(self):
        def gen():
            value = 'old'
            try:
                (value := (yield 'ready'))
            except ValueError:
                yield value
        iterator = gen()
        self.assertEqual(next(iterator), 'ready')
        self.assertEqual(iterator.throw(ValueError('marker')), 'old')
        iterator.close()

    def test_generator_result_in_pending_call(self):
        def collect(*args):
            return args
        def gen():
            yield collect(value := object(), (yield 'ready'))
            yield value
        iterator = gen()
        self.assertEqual(next(iterator), 'ready')
        pair = iterator.send(42)
        self.assertEqual(pair[1], 42)
        self.assertIs(next(iterator), pair[0])
        iterator.close()

    def test_legacy_call_stack_across_yield(self):
        for expression in ('collect(1, (yield 0))', 'collect(1, 2, (yield 0))',
                           'collect(1, 2, 3, (yield 0))', 'collect(collect(1, (yield 0)), 2)',
                           'box.collect(1, 2, (yield 0))'):
            class Box(object):
                def collect(self, *args):
                    return args
            ns = {'collect': lambda *args: args, 'box': Box()}
            execute('def gen():\n yield ' + expression + '\niterator = gen()', ns)
            iterator = ns['iterator']
            self.assertEqual(next(iterator), 0)
            result = iterator.send(42)
            self.assertIsInstance(result, tuple)
            self.assertIn('42', repr(result))
            iterator.close()

    def test_binary_and_subscript_stack_across_yield(self):
        def gen():
            yield 10 + (value := (yield 0))
            yield [1, 2, 3][index := (yield 1)]
        iterator = gen()
        self.assertEqual(next(iterator), 0)
        self.assertEqual(iterator.send(32), 42)
        self.assertEqual(next(iterator), 1)
        self.assertEqual(iterator.send(2), 3)
        iterator.close()

    def test_comprehension_as_rhs(self):
        self.assertEqual((values := [n * 2 for n in [1, 2]]), [2, 4])
        self.assertEqual(values, [2, 4])
        self.assertEqual(list(generator := (n for n in [1, 2])), [1, 2])

    def test_ast_shape_and_context(self):
        tree = ast.parse('result = (value := source)\n')
        node = tree.body[0].value
        self.assertIsInstance(node, ast.NamedExpr)
        self.assertIsInstance(node.target, ast.Name)
        self.assertIsInstance(node.target.ctx, ast.Store)
        self.assertIsInstance(node.value.ctx, ast.Load)
        self.assertEqual(tuple(node._fields), ('target', 'value'))
        self.assertEqual((node.lineno, node.col_offset), (1, 10))
        source = object()
        ns = {'source': source}
        eval(compile(tree, '<ast>', 'exec'), ns)
        self.assertIs(ns['result'], source)
        self.assertIs(ns['value'], source)

    def test_manual_ast_and_subclass(self):
        class Custom(ast.NamedExpr):
            pass
        literal = ast.parse('42', mode='eval').body
        marker = Custom(target=ast.Name(id='value', ctx=ast.Store()), value=literal)
        marker.extra = 1
        tree = ast.fix_missing_locations(ast.Expression(body=marker))
        before = ast.dump(tree)
        ns = {}
        self.assertEqual(eval(compile(tree, '<manual>', 'eval'), ns), 42)
        self.assertEqual(ns['value'], 42)
        self.assertEqual(ast.dump(tree), before)
        self.assertEqual(marker.extra, 1)

    def test_interactive(self):
        self.assertIsNone(codeop.compile_command('(value := '))
        self.assertIsNone(codeop.compile_command('if value := 1:'))
        self.assertIsNone(codeop.compile_command('@deco := lambda f:f\ndef f():'))
        self.assertIsNotNone(codeop.compile_command('(value := 42)'))
        ns = {}
        eval(codeop.compile_command('if value := 1:\n result = value\n'), ns)
        self.assertEqual((ns['value'], ns['result']), (1, 1))

    def test_tokenize_roundtrip(self):
        source = u'if value := 1:\n result = {"a": (other := 2)}\n'
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        operators = [item[1] for item in tokens if item[0] == tokenize.OP]
        self.assertEqual(operators.count(':='), 2)
        self.assertEqual(operators.count(':'), 2)
        self.assertEqual(tokenize.untokenize(tokens), source)

    def test_parentheses_required(self):
        cases = ('value := 1', 'result = value := 1', 'return value := 1',
                 'assert value := 1', 'lambda: value := 1', 'f(key=value := 1)',
                 'f(*value := [1])', 'f(**value := {})', '{value := 1: 2}',
                 '{1: value := 2}', 'a[value := 1:]', 'a[:value := 2]',
                 'a[::value := 1]', 'a if value := 1 else b', 'with value := cm: pass')
        for source in cases:
            with self.assertRaises(SyntaxError):
                compile(source, '<parentheses>', 'exec')

    def test_invalid_targets_and_chaining(self):
        cases = ('(a.b := 1)', '(a[0] := 1)', '((a, b) := 1)', '([a] := 1)',
                 '((a) := 1)', '(1 := 2)', '(None := 1)', '(True := 1)',
                 '(False := 1)', '(__debug__ := 1)', '(a := b := 1)',
                 '(a := 1) = 2', '(a := 1) += 2', 'del (a := 1)', 'f(a := 1 = 2)')
        for source in cases:
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid-target>', 'exec')

    def test_declaration_order(self):
        for source in ('def f():\n (value := 1)\n global value',
                       'def outer():\n value = 0\n def f():\n  (value := 1)\n  nonlocal value'):
            with self.assertRaises(SyntaxError):
                compile(source, '<declaration>', 'exec')


@unittest.skipUnless(IS_JYTHON, 'native AST validation and explicit migration boundaries')
class NativeNamedExpressionTests(unittest.TestCase):
    def test_comprehensions_rejected_explicitly(self):
        cases = ('[value := n for n in [1]]', '{(value := n) for n in [1]}',
                 '{n: (value := n) for n in [1]}', '(value := n for n in [1])',
                 '[n for n in [1] if (value := n)]', '[n for n in (values := [1])]',
                 '[lambda: (value := n) for n in [1]]')
        for source in cases:
            with self.assertRaises(SyntaxError) as caught:
                compile(source, '<comprehension-boundary>', 'eval')
            self.assertIn('modern comprehension scopes', str(caught.exception))

    def test_invalid_ast_contexts(self):
        for target in (ast.Name(id='x', ctx=ast.Load()), ast.Num(n=1), None):
            tree = ast.parse('(x := 1)', mode='eval')
            tree.body.target = target
            with self.assertRaises(SyntaxError):
                compile(tree, '<bad-target>', 'eval')
        for value in (ast.Name(id='x', ctx=ast.Store()), None):
            tree = ast.parse('(x := 1)', mode='eval')
            tree.body.value = value
            with self.assertRaises(SyntaxError):
                compile(tree, '<bad-value>', 'eval')

    def test_ast_namedexpr_not_assignable(self):
        for source in ('x = 1', 'x += 1', 'del x', 'for x in []: pass'):
            tree = ast.parse(source)
            node = ast.parse('(x := 1)', mode='eval').body
            if hasattr(tree.body[0], 'targets'):
                tree.body[0].targets = [node]
            else:
                tree.body[0].target = node
            with self.assertRaises(SyntaxError):
                compile(tree, '<bad-ast-target>', 'exec')

    def test_java_identity(self):
        from java.util import ArrayList
        original = ArrayList()
        self.assertIs((items := original), original)
        items.add('native')
        self.assertEqual(original.get(0), 'native')

    def test_java_subclass_method(self):
        from java.util import ArrayList
        class Values(ArrayList):
            def first(self):
                return (value := self.get(0)), value
        values = Values()
        values.add(42)
        self.assertEqual(values.first(), (42, 42))

    def test_native_locations_and_tokens(self):
        import token
        node = ast.NamedExpr(ast.Name(id='x', ctx=ast.Store()), ast.Num(n=1), lineno=7, col_offset=3)
        self.assertEqual((node.lineno, node.col_offset), (7, 3))
        self.assertEqual((token.AT, token.ATEQUAL, token.COLONEQUAL), (50, 53, 54))


def test_main():
    from test import test_support
    test_support.run_unittest(NamedExpressionTests, NativeNamedExpressionTests)


if __name__ == '__main__':
    unittest.main()
