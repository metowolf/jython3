"""Native Python 3 function syntax on the transitional Jython runtime.

The shared cases also run on CPython 3.8-3.13. This is not a claim of
whole-language or Python 3 standard-library compatibility.
"""
import ast
import codeop
import sys
import types
import unittest

IS_JYTHON = sys.platform.startswith('java')


class FunctionSyntaxTest(unittest.TestCase):

    def test_keyword_only_required_and_none(self):
        def f(*, required, optional=None):
            return required, optional
        self.assertEqual(f(required=1), (1, None))
        self.assertEqual(f(optional=2, required=1), (1, 2))
        self.assertEqual(f.__kwdefaults__, {'optional': None})
        self.assertRaises(TypeError, f)
        self.assertRaises(TypeError, f, 1)
        self.assertRaises(TypeError, f, required=1, extra=2)

    def test_all_parameter_kinds(self):
        def f(a, /, b=2, *rest, required, option=3, **extras):
            return a, b, rest, required, option, extras
        self.assertEqual(f(1, 4, 5, 6, required=7, option=8, a=9),
                         (1, 4, (5, 6), 7, 8, {'a': 9}))
        self.assertEqual(f(1, required=7), (1, 2, (), 7, 3, {}))
        self.assertRaises(TypeError, f, 1, 2, b=3, required=4)
        self.assertRaises(TypeError, f, a=1, required=4)

    def test_posonly_defaults(self):
        def f(a=1, /, b=2):
            return a, b
        self.assertEqual(f(), (1, 2))
        self.assertEqual(f(3), (3, 2))
        self.assertEqual(f(b=4), (1, 4))
        self.assertRaises(TypeError, f, a=4)

    def test_posonly_name_in_kwargs(self):
        def f(a=1, /, **kw):
            return a, kw
        self.assertEqual(f(a=2), (1, {'a': 2}))
        self.assertEqual(f(3, a=2), (3, {'a': 2}))

    def test_code_metadata(self):
        def f(a, /, b=2, *rest, c, d=4, **kw):
            return a, b, rest, c, d, kw
        code = f.__code__
        self.assertEqual(code.co_argcount, 2)
        self.assertEqual(code.co_posonlyargcount, 1)
        self.assertEqual(code.co_kwonlyargcount, 2)
        self.assertEqual(code.co_varnames[:6], ('a', 'b', 'c', 'd', 'rest', 'kw'))
        self.assertEqual(code.co_flags & 12, 12)
        self.assertRaises((TypeError, AttributeError), setattr, code, 'co_kwonlyargcount', 0)

    def test_fixed_arity_dispatch(self):
        def f(*args, flag=17):
            return args, flag
        self.assertEqual(f(), ((), 17))
        self.assertEqual(f(1), ((1,), 17))
        self.assertEqual(f(1, 2), ((1, 2), 17))
        self.assertEqual(f(1, 2, 3), ((1, 2, 3), 17))
        self.assertEqual(f(1, 2, 3, 4), ((1, 2, 3, 4), 17))
        self.assertEqual(f(1, 2, 3, 4, 5), ((1, 2, 3, 4, 5), 17))
        self.assertEqual(f(*(1, 2)), ((1, 2), 17))
        self.assertEqual(f.__call__(flag=18), ((), 18))

    def test_bound_method_dispatch(self):
        class C(object):
            def f(self, /, *args, flag=17, **kw):
                return args, flag, kw
        c = C()
        self.assertEqual(c.f(), ((), 17, {}))
        self.assertEqual(c.f(1), ((1,), 17, {}))
        self.assertEqual(c.f(1, 2, 3), ((1, 2, 3), 17, {}))
        self.assertEqual(c.f(1, 2, 3, 4), ((1, 2, 3, 4), 17, {}))
        self.assertEqual(c.f(1, flag=18, other=2), ((1,), 18, {'other': 2}))
        self.assertEqual(c.f(*(1, 2), **{'flag': 19}), ((1, 2), 19, {}))

    def test_lambda(self):
        f = lambda a, /, b=2, *, c=3: (a, b, c)
        self.assertEqual(f(1), (1, 2, 3))
        self.assertEqual(f(1, c=4), (1, 2, 4))
        self.assertRaises(TypeError, f, a=1)
        g = lambda *args, required, **kw: (args, required, kw)
        self.assertEqual(g(1, required=2, other=3), ((1,), 2, {'other': 3}))
        self.assertRaises(TypeError, g)
        self.assertEqual((lambda x: x)(4), 4)
        self.assertEqual((lambda: 5)(), 5)
        self.assertEqual((lambda x=lambda y: y: x)()(6), 6)
        self.assertEqual((lambda *, f=lambda x: x: f)()(7), 7)

    def test_mutable_default_evaluated_once(self):
        def f(*, value=[]):
            value.append(len(value))
            return value
        self.assertEqual(f(), [0])
        self.assertEqual(f(), [0, 1])
        self.assertIs(f.__kwdefaults__['value'], f())

    def test_annotations(self):
        def f(a: int, /, b: str='b', *args: tuple, c: float=1.0,
              **kw: dict) -> bool:
            return True
        self.assertEqual(f.__annotations__, {'a': int, 'b': str, 'args': tuple,
                                            'c': float, 'kw': dict, 'return': bool})
        self.assertTrue(f(object()))
        def empty():
            pass
        self.assertEqual(empty.__annotations__, {})
        self.assertIsNone(empty.__kwdefaults__)
        def only_return() -> None:
            pass
        self.assertEqual(only_return.__annotations__, {'return': None})

    def test_definition_evaluation_order(self):
        events = []
        def value(name):
            events.append(name)
            return name
        def decorator(name):
            events.append(name)
            def apply(f):
                events.append('apply-' + name)
                self.assertEqual(f.__kwdefaults__, {'k': 'kw-default'})
                self.assertEqual(f.__annotations__['return'], 'return')
                return f
            return apply
        @decorator('outer')
        @decorator('inner')
        def f(a: value('a')=value('default'),
              *, k: value('k')=value('kw-default')) -> value('return'):
            pass
        self.assertEqual(events, ['outer', 'inner', 'default', 'kw-default',
                                  'a', 'k', 'return', 'apply-inner', 'apply-outer'])

    def test_definition_scope_and_closure(self):
        def outer():
            annotation = object()
            default = object()
            def middle():
                def f(a: annotation, *, b=default) -> annotation:
                    return a, b
                return f
            return middle, annotation, default
        middle, annotation, default = outer()
        f = middle()
        self.assertIs(f.__annotations__['a'], annotation)
        self.assertIs(f.__annotations__['return'], annotation)
        self.assertIs(f(1)[1], default)
        def captured(*, item=3):
            return lambda: item
        self.assertEqual(captured()(), 3)
        self.assertEqual(captured(item=5)(), 5)

    def test_class_definition_scope(self):
        class C(object):
            annotation = object()
            default = object()
            def f(self, a: annotation, *, b=default) -> annotation:
                return b
        self.assertIs(C.f.__annotations__['a'], C.annotation)
        self.assertIs(C().f(1), C.default)

    def test_generator_binding(self):
        def f(a, /, *args, required, option=3, **kw):
            yield a, args, required, option, kw
        self.assertEqual(next(f(1, 2, required=4, extra=5)), (1, (2,), 4, 3, {'extra': 5}))
        self.assertRaises(TypeError, f, 1)

    def test_yield_in_definition_expressions(self):
        def outer():
            def f(a: (yield 'annotation')=(yield 'default'),
                  *, k=(yield 'kw-default')) -> (yield 'return'):
                return a, k
            yield f
        g = outer()
        self.assertEqual(next(g), 'default')
        self.assertEqual(g.send(10), 'kw-default')
        self.assertEqual(g.send(20), 'annotation')
        self.assertEqual(g.send(int), 'return')
        f = g.send(tuple)
        self.assertEqual(f(), (10, 20))
        self.assertEqual(f.__annotations__, {'a': int, 'return': tuple})

    def test_lambda_yield_default(self):
        def outer():
            yield lambda *, k=(yield 'default'): k
        g = outer()
        self.assertEqual(next(g), 'default')
        self.assertEqual(g.send(9)(), 9)

    def test_attribute_mutation(self):
        def f(*, k=1):
            return k
        f.__kwdefaults__['k'] = 2
        self.assertEqual(f(), 2)
        f.__kwdefaults__ = {'k': None}
        self.assertIsNone(f())
        del f.__kwdefaults__
        self.assertIsNone(f.__kwdefaults__)
        self.assertRaises(TypeError, f)
        f.__kwdefaults__ = None
        self.assertRaises(TypeError, setattr, f, '__kwdefaults__', ())
        f.__annotations__ = {'k': int}
        self.assertEqual(f.__annotations__, {'k': int})
        del f.__annotations__
        self.assertEqual(f.__annotations__, {})
        f.__annotations__ = None
        self.assertEqual(f.__annotations__, {})
        self.assertRaises(TypeError, setattr, f, '__annotations__', [])

    def test_function_constructor_and_code_replacement(self):
        def f(*, k=1):
            return k
        copy = types.FunctionType(f.__code__, globals())
        self.assertRaises(TypeError, copy)
        copy.__kwdefaults__ = {'k': 7}
        self.assertEqual(copy(), 7)
        def plain():
            return 9
        plain.__code__ = f.__code__
        self.assertRaises(TypeError, plain)
        plain.__kwdefaults__ = {'k': 8}
        self.assertEqual(plain(), 8)

    def test_invalid_signatures(self):
        signatures = ['/', 'a, /, /', 'a, /, b, /', '*, /', '*a, /',
                      '*', '*, **kw', '*a, *b', '**kw, a', '**kw, *a',
                      '**a, **b', 'a=1, /, b', 'a=1, b', 'a, *, a',
                      'a, /, a', '*a, a', '*a, **a', '*, a, **a',
                      '*a=1', '**kw=1', 'None', '__debug__', '*None',
                      '**__debug__', 'a,, b', 'a:']
        for signature in signatures:
            source = 'def f(%s):\n    pass\n' % signature
            with self.assertRaises(SyntaxError, msg=source):
                compile(source, '<invalid-signature>', 'exec')
        for source in ['lambda a: int: a', 'lambda *a: int: a',
                       'def f() - > int:\n    pass\n']:
            with self.assertRaises(SyntaxError, msg=source):
                compile(source, '<invalid-signature>', 'exec')

    def test_interactive_headers(self):
        for source in ['def f(a: int, /, *, b=1) -> int:',
                       'def f(*args: int, k, **kw: dict):',
                       'def f(a, /, b=2, *, k):\n    return a']:
            self.assertIsNone(codeop.compile_command(source))
        self.assertIsNotNone(codeop.compile_command(
            'def f(a: int, /, *, b=1) -> int:\n    return a + b\n'))

    def test_ast_roundtrip(self):
        tree = ast.parse('def f(a: int, /, b=2, *, required, k=None) -> str:\n'
                         '    return a, b, required, k\n')
        node = tree.body[0]
        self.assertEqual(len(node.args.posonlyargs), 1)
        self.assertEqual(len(node.args.args), 1)
        self.assertEqual(len(node.args.kwonlyargs), 2)
        self.assertIsNone(node.args.kw_defaults[0])
        self.assertIsNotNone(node.args.kw_defaults[1])
        self.assertEqual(node.returns.id, 'str')
        namespace = {}
        eval(compile(tree, '<ast>', 'exec'), namespace)
        self.assertEqual(namespace['f'](1, required=3), (1, 2, 3, None))
        self.assertEqual(namespace['f'].__annotations__, {'a': int, 'return': str})

    def test_ast_mutation(self):
        tree = ast.parse('def f(a, /, *, k) -> int:\n    return a, k\n')
        node = tree.body[0]
        node.args.kw_defaults[0] = ast.Num(9)
        node.returns = ast.Name('tuple', ast.Load())
        ast.fix_missing_locations(tree)
        namespace = {}
        eval(compile(tree, '<modified-ast>', 'exec'), namespace)
        f = namespace['f']
        self.assertEqual(f(1), (1, 9))
        self.assertEqual(f.__kwdefaults__, {'k': 9})
        self.assertEqual(f.__annotations__, {'return': tuple})
        self.assertRaises(TypeError, f, a=1)

    @unittest.skipUnless(IS_JYTHON, 'transitional Jython AST')
    def test_legacy_ast_constructor(self):
        args = ast.arguments([], None, None, [])
        self.assertEqual(list(args.posonlyargs), [])
        self.assertEqual(list(args.kwonlyargs), [])
        self.assertEqual(list(args.kw_defaults), [])
        self.assertEqual(list(args.annotations), [])
        node = ast.FunctionDef('f', args, [ast.Pass()], [])
        self.assertIsNone(node.returns)
        tree = ast.fix_missing_locations(ast.Module([node]))
        namespace = {}
        eval(compile(tree, '<legacy-ast>', 'exec'), namespace)
        self.assertIsNone(namespace['f']())

    @unittest.skipUnless(IS_JYTHON, 'legacy syntax retained during migration')
    def test_legacy_tuple_parameters(self):
        namespace = {}
        eval(compile('def f((a, b), c=3, *args, **kw):\n'
                     '    return a, b, c, args, kw\n', '<legacy>', 'exec'), namespace)
        self.assertEqual(namespace['f']((1, 2), 4, 5, x=6), (1, 2, 4, (5,), {'x': 6}))

    @unittest.skipUnless(IS_JYTHON, 'Java functional interface')
    def test_java_interface(self):
        from java.util.concurrent import FutureTask
        def f(*, result=42):
            return result
        task = FutureTask(f)
        task.run()
        self.assertEqual(task.get(), 42)


def test_main():
    from test import test_support
    test_support.run_unittest(FunctionSyntaxTest)


if __name__ == '__main__':
    unittest.main()
