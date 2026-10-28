"""Native expression decorators; shared semantics checked on CPython 3.15.2."""
import ast
import codeop
import sys
import unittest

IS_JYTHON = sys.platform.startswith('java')


def identity(value):
    return value


def execute(source, namespace=None):
    if namespace is None:
        namespace = {'__name__': __name__}
    eval(compile(source, '<expression-decorator>', 'exec'), namespace)
    return namespace


def define(expression, kind='function', namespace=None):
    if namespace is None:
        namespace = {'d': identity, '__name__': __name__}
    body = 'def target(): return 42' if kind == 'function' else 'class target(object): pass'
    execute('@' + expression + '\n' + body, namespace)
    return namespace['target']


class DecoratorExpressionTests(unittest.TestCase):
    def check_expression(self, expression):
        self.assertEqual(define(expression)(), 42)
        self.assertIsInstance(define(expression), type(identity))
        cls = define(expression, 'class')
        self.assertIsInstance(cls(), cls)

    def test_subscript(self):
        self.check_expression('[d][0]')
        self.check_expression('{"key": d}["key"]')

    def test_parenthesized(self):
        self.check_expression('(((d)))')

    def test_bare_lambda(self):
        self.check_expression('lambda value: value')

    def test_conditional(self):
        self.check_expression('d if True else missing')
        self.check_expression('missing if False else d')

    def test_boolean_short_circuit(self):
        self.check_expression('d or missing')
        self.check_expression('False or d')
        self.check_expression('True and d')

    def test_chained_call(self):
        self.check_expression('(lambda: lambda: d)()()')

    def test_call_then_attribute(self):
        class Factory(object):
            decorator = staticmethod(identity)
        for kind in ('function', 'class'):
            target = define('Factory().decorator', kind, {'Factory': Factory})
            self.assertEqual(target.__name__, 'target')

    def test_subscript_after_slice(self):
        self.check_expression('[None, d][1:][0]')

    def test_parenthesized_tuple(self):
        self.check_expression('(None, d)[1]')

    def test_comprehensions(self):
        self.check_expression('[item for item in [d]][0]')
        self.check_expression('{key: d for key in [1]}[1]')
        self.check_expression('next(item for item in [d])')
        self.check_expression('next(iter({item for item in [d]}))')

    def test_expanded_displays(self):
        self.check_expression('[*[], *[d]][0]')
        self.check_expression('{**{}, "d": d}["d"]')

    def test_expanded_calls(self):
        self.check_expression('(lambda *a, **kw: kw["d"])(*[], **{}, d=d, **{})')

    def test_multiline(self):
        self.check_expression('(\n [d]\n [0]\n)')
        self.check_expression('[\n d,\n][0] # comment')

    def test_explicit_line_continuation(self):
        self.check_expression('d if True \\\n else missing')

    def test_binary_operator(self):
        events = []
        class Operand(object):
            def __add__(self, other):
                events.append(other)
                return identity
        target = define('operand + 7', namespace={'operand': Operand()})
        self.assertEqual(target(), 42)
        self.assertEqual(events, [7])

    def test_lookup_occurs_once(self):
        events = []
        class Registry(object):
            def __getitem__(self, key):
                events.append(key)
                return identity
        define('registry["d"]', namespace={'registry': Registry()})
        self.assertEqual(events, ['d'])

    def test_function_evaluation_and_application_order(self):
        events = []
        def mark(label, value):
            events.append(label)
            return value
        def decorator(label):
            events.append('evaluate ' + label)
            def apply(func):
                events.append('apply ' + label)
                return func
            return apply
        namespace = {'events': events, 'mark': mark, 'decorator': decorator}
        execute('@[decorator("outer")][0]\n@decorator("inner") if True else missing\n'
                'def f(x=mark("default", 1), *, k=mark("keyword", 2)):\n'
                ' events.append("body")\n return x + k', namespace)
        self.assertEqual(events, ['evaluate outer', 'evaluate inner', 'default',
                                  'keyword', 'apply inner', 'apply outer'])
        self.assertEqual(namespace['f'](), 3)
        self.assertEqual(events[-1], 'body')

    def test_class_evaluation_and_application_order(self):
        events = []
        def decorator(label):
            events.append('evaluate ' + label)
            def apply(cls):
                events.append('apply ' + label)
                return cls
            return apply
        def bases():
            events.append('bases')
            return [object]
        namespace = {'events': events, 'decorator': decorator, 'bases': bases}
        execute('@[decorator("outer")][0]\n@(lambda: decorator("inner"))()\n'
                'class C(*bases()):\n events.append("body")', namespace)
        self.assertEqual(events, ['evaluate outer', 'evaluate inner', 'bases',
                                  'body', 'apply inner', 'apply outer'])

    def test_replacement_and_composition(self):
        marker = object()
        seen = []
        def outer(value):
            seen.append(value)
            return 'replaced'
        for kind in ('function', 'class'):
            body = 'def target(): pass' if kind == 'function' else 'class target(object): pass'
            namespace = {'outer': outer, 'marker': marker}
            execute('@[outer][0]\n@lambda value: marker\n' + body, namespace)
            self.assertEqual(namespace['target'], 'replaced')
        self.assertEqual(seen, [marker, marker])

    def test_evaluation_failure_stops_definition(self):
        for kind in ('function', 'class'):
            marker = object()
            events = []
            namespace = {'target': marker, 'events': events}
            suffix = ('def target(x=events.append("default")): pass' if kind == 'function'
                      else 'class target(object):\n events.append("body")')
            with self.assertRaises(ZeroDivisionError):
                execute('@[1 / 0][0]\n' + suffix, namespace)
            self.assertIs(namespace['target'], marker)
            self.assertEqual(events, [])

    def test_application_failure_preserves_binding(self):
        def fail(value):
            raise RuntimeError('application')
        for kind in ('function', 'class'):
            marker = object()
            namespace = {'target': marker, 'fail': fail}
            with self.assertRaises(RuntimeError):
                define('[fail][0]', kind, namespace)
            self.assertIs(namespace['target'], marker)

    def test_non_callable_is_runtime_error(self):
        for expr in ('1 + 2', '(identity, identity)', '[identity]', 'None'):
            for kind in ('function', 'class'):
                with self.assertRaises(TypeError):
                    define(expr, kind, {'identity': identity})

    def test_previous_binding_visible(self):
        for kind in ('function', 'class'):
            namespace = {'target': identity}
            value = define('[target][0]', kind, namespace)
            self.assertIsNot(value, identity)
            self.assertEqual(value.__name__, 'target')

    def test_closure_scope(self):
        def outer():
            decorators = [identity]
            marker = object()
            @decorators[0]
            def function():
                return marker
            @decorators[0]
            class C(object):
                def value(self):
                    return marker
            return function, C, marker
        func, cls, marker = outer()
        self.assertIs(func(), marker)
        self.assertIs(cls().value(), marker)

    def test_class_scope_and_descriptors(self):
        class C(object):
            decorators = [staticmethod, classmethod, property]
            @decorators[0]
            def static():
                return 1
            @decorators[1]
            def cls(cls):
                return cls
            @decorators[2]
            def value(self):
                return 3
        self.assertEqual(C.static(), 1)
        self.assertIs(C.cls(), C)
        self.assertEqual(C().value, 3)

    def test_nonlocal_binding(self):
        target = None
        def bind():
            nonlocal target
            @[identity][0]
            def target():
                return 12
        bind()
        self.assertEqual(target(), 12)

    def test_generator_suspension(self):
        def gen():
            @(yield 'outer')
            @(yield 'inner')
            def f(value=(yield 'default')):
                return value
            yield f
        events = []
        def wrap(label):
            def apply(value):
                events.append(label)
                return value
            return apply
        iterator = gen()
        self.assertEqual(next(iterator), 'outer')
        self.assertEqual(iterator.send(wrap('outer')), 'inner')
        self.assertEqual(iterator.send(wrap('inner')), 'default')
        self.assertEqual(events, [])
        function = iterator.send(42)
        self.assertEqual(function(), 42)
        self.assertEqual(events, ['inner', 'outer'])
        iterator.close()

    def test_class_generator_suspension(self):
        def gen():
            @[(yield 'decorator')][0]
            class C(*(yield 'bases')):
                pass
            yield C
        iterator = gen()
        self.assertEqual(next(iterator), 'decorator')
        self.assertEqual(iterator.send(identity), 'bases')
        cls = iterator.send([object])
        self.assertEqual(cls.__bases__, (object,))
        iterator.close()

    def test_generator_throw_and_close(self):
        events = []
        def gen():
            try:
                @(yield 'decorator')
                def f(value=events.append('unexpected')):
                    pass
            finally:
                events.append('closed')
        iterator = gen()
        next(iterator)
        iterator.close()
        iterator = gen()
        next(iterator)
        with self.assertRaises(RuntimeError):
            iterator.throw(RuntimeError('stop'))
        self.assertEqual(events, ['closed', 'closed'])

    def test_ast_shape_and_roundtrip(self):
        for kind, header in (('function', 'def target(): return 42'),
                             ('class', 'class target(object): pass')):
            source = '@[d][0]\n@d if True else missing\n' + header
            tree = ast.parse(source)
            first, second = tree.body[0].decorator_list
            self.assertIsInstance(first, ast.Subscript)
            self.assertIsInstance(first.ctx, ast.Load)
            self.assertIsInstance(second, ast.IfExp)
            self.assertEqual((first.lineno, first.col_offset), (1, 1))
            self.assertEqual((second.lineno, second.col_offset), (2, 1))
            namespace = {'d': identity}
            eval(compile(tree, '<decorator-ast>', 'exec'), namespace)
            self.assertEqual(namespace['target'].__name__, 'target')

    def test_interactive_input(self):
        for source in ('@[d][', '@(d', '@[d][0]', '@lambda f: f',
                       '@[d][0]\ndef f():', '@[d][0]\nclass C:'):
            self.assertIsNone(codeop.compile_command(source))
        source = '@[d][0]\ndef f():\n return 42\n'
        code = codeop.compile_command(source)
        self.assertIsNotNone(code)
        namespace = {'d': identity}
        eval(code, namespace)
        self.assertEqual(namespace['f'](), 42)

    def test_invalid_syntax(self):
        for source in ('@d, d\ndef f(): pass', '@*d\ndef f(): pass',
                       '@d; d\ndef f(): pass', '@\ndef f(): pass',
                       '@d\nx = 1', '@yield d\ndef f(): pass',
                       '@(yield d)\ndef f(): pass', '@d = 1\ndef f(): pass'):
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid-decorator>', 'exec')

    def test_long_stack(self):
        namespace = {'d': identity}
        execute('@[d][0]\n' * 80 + 'def target(): return 42', namespace)
        self.assertEqual(namespace['target'](), 42)


@unittest.skipUnless(IS_JYTHON, 'native JVM AST and Java integration')
class NativeDecoratorExpressionTests(unittest.TestCase):
    def test_java_list_lookup(self):
        from java.util import ArrayList
        decorators = ArrayList()
        decorators.add(identity)
        target = define('decorators[0]', namespace={'decorators': decorators})
        self.assertEqual(target(), 42)
        self.assertEqual(decorators.size(), 1)

    def test_decorated_java_subclass(self):
        from java.util import ArrayList
        namespace = {'ArrayList': ArrayList, 'd': identity}
        execute('@[d][0]\nclass C(*[ArrayList]): pass\nobj = C()', namespace)
        namespace['obj'].add('native')
        self.assertEqual(namespace['obj'].get(0), 'native')
        self.assertIsInstance(namespace['obj'], ArrayList)

    def test_invalid_ast_contexts(self):
        for header in ('def f(): pass', 'class C(object): pass'):
            for expression in ('d', 'd.attr', 'd[0]', '[d]', '(d,)'):
                for context in (ast.Store(), ast.Del()):
                    tree = ast.parse('@' + expression + '\n' + header)
                    tree.body[0].decorator_list[0].ctx = context
                    with self.assertRaises(SyntaxError):
                        compile(tree, '<bad-context>', 'exec')

    def test_missing_and_bare_star_ast(self):
        for header in ('def f(): pass', 'class C(object): pass'):
            for value in (None, ast.Starred(value=ast.Name(id='d', ctx=ast.Load()),
                                            ctx=ast.Load())):
                tree = ast.parse('@d\n' + header)
                tree.body[0].decorator_list = [value]
                with self.assertRaises(SyntaxError):
                    compile(ast.fix_missing_locations(tree), '<bad-decorator>', 'exec')

    def test_unreachable_ast_validation(self):
        for header in ('def f(): pass', 'class C(object): pass'):
            tree = ast.parse('if False:\n @d\n ' + header)
            tree.body[0].body[0].decorator_list = [None]
            with self.assertRaises(SyntaxError):
                compile(tree, '<unreachable-decorator>', 'exec')

    def test_unimplemented_expression_forms(self):
        class Factory(object):
            def __matmul__(self, other):
                return identity
        self.assertEqual(define('a @ b', namespace={'a': Factory(), 'b': object()})(), 42)
        for expression in ('(assigned := identity)', 'await identity()'):
            with self.assertRaises(SyntaxError):
                compile('@' + expression + '\ndef f(): pass', '<unsupported>', 'exec')


def test_main():
    from test import test_support
    test_support.run_unittest(DecoratorExpressionTests, NativeDecoratorExpressionTests)


if __name__ == '__main__':
    unittest.main()
