"""Python 3 nonlocal and closure-cell deletion regressions."""
import ast
import codeop
import unittest


class NonlocalTest(unittest.TestCase):
    def test_shared_cell(self):
        value = 0
        def increment(*, amount=1):
            nonlocal value
            value += amount
            return value
        def read():
            return value
        self.assertEqual(increment(), 1)
        self.assertEqual(increment(amount=4), 5)
        self.assertEqual(read(), 5)
        self.assertIn('value', increment.__code__.co_freevars)
        self.assertNotIn('value', increment.__code__.co_varnames)
        self.assertIs(increment.__closure__[0], read.__closure__[0])

    def test_multiple_and_repeated_declarations(self):
        a, b = 1, 2
        def change():
            nonlocal a, b, a
            nonlocal a
            a, b = b, a
            return a, b
        self.assertEqual(change(), (2, 1))
        self.assertEqual((a, b), (2, 1))

    def test_nearest_binding_and_passthrough(self):
        value = 'outer'
        def middle():
            value = 'middle'
            def passthrough():
                def change():
                    nonlocal value
                    value = 'changed'
                return change
            passthrough()()
            return value
        self.assertEqual(middle(), 'changed')
        self.assertEqual(value, 'outer')

    def test_nonlocal_propagates_to_children(self):
        value = 1
        def middle():
            nonlocal value
            def child():
                nonlocal value
                value += 1
            def read():
                return value
            child()
            return read
        self.assertEqual(middle()(), 2)
        self.assertEqual(value, 2)

    def test_later_and_conditional_bindings(self):
        def outer():
            def change():
                nonlocal value
                value = 2
            value = 1
            change()
            return value
        self.assertEqual(outer(), 2)
        def uninitialized():
            if False:
                value = 1
            def change():
                nonlocal value
                value = 3
                return value
            return change
        self.assertEqual(uninitialized()(), 3)

    def test_parameter_binding(self):
        def outer(value, /, *, other=2):
            def change():
                nonlocal value, other
                value += other
                other += 1
                return value, other
            return change
        change = outer(1)
        self.assertEqual(change(), (3, 3))
        self.assertEqual(change(), (6, 4))

    def test_class_namespace_is_skipped(self):
        value = 1
        class C(object):
            value = 9
            def change(self):
                nonlocal value
                value = 2
        C().change()
        self.assertEqual(value, 2)
        self.assertEqual(C.value, 9)

    def test_class_body_nonlocal(self):
        value = 1
        class C(object):
            nonlocal value
            value += 2
            observed = value
            def read(self):
                return value
        self.assertEqual(value, 3)
        self.assertEqual(C.observed, 3)
        self.assertEqual(C().read(), 3)
        self.assertNotIn('value', C.__dict__)

    def test_generator(self):
        value = 0
        def generate():
            nonlocal value
            for i in range(3):
                value += 1
                yield value
        g = generate()
        self.assertEqual(next(g), 1)
        self.assertEqual(value, 1)
        self.assertEqual(list(g), [2, 3])
        self.assertEqual(value, 3)

    def test_delete_and_rebind(self):
        value = 1
        def remove():
            nonlocal value
            del value
        def read():
            return value
        def assign():
            nonlocal value
            value = 4
        remove()
        with self.assertRaises(NameError) as error:
            read()
        self.assertIs(type(error.exception), NameError)
        self.assertRaises(NameError, remove)
        try:
            value
        except UnboundLocalError:
            pass
        else:
            self.fail('local cell should be empty')
        assign()
        self.assertEqual(read(), 4)
        self.assertEqual(value, 4)

    def test_delete_local_cell(self):
        value = 1
        def read():
            return value
        del value
        self.assertRaises(NameError, read)
        try:
            del value
        except UnboundLocalError:
            pass
        else:
            self.fail('deleting an empty local cell must fail')
        value = 2
        self.assertEqual(read(), 2)

    def test_definition_and_import_bindings(self):
        item = None
        def change():
            nonlocal item
            import math as item
        change()
        self.assertEqual(item.sqrt(9), 3)
        def define():
            nonlocal item
            def item():
                return 7
        define()
        self.assertEqual(item(), 7)

    def test_invalid_declarations(self):
        invalid = [
            'nonlocal x',
            'x=1\ndef f():\n nonlocal x',
            'def f(x):\n nonlocal x',
            'def f():\n nonlocal x',
            'class C:\n x=1\n def f(self):\n  nonlocal x',
            'def o():\n x=1\n def f():\n  x=2\n  nonlocal x',
            'def o():\n x=1\n def f():\n  x\n  nonlocal x',
            'def o():\n x=1\n def f():\n  del x\n  nonlocal x',
            'def o():\n x=1\n def f():\n  global x\n  nonlocal x',
            'def o():\n x=1\n def f():\n  nonlocal x\n  global x',
            'def o():\n x=1\n def m():\n  global x\n  def f():\n   nonlocal x',
            'def o():\n x=1\n def f():\n  nonlocal x,',
            'def o():\n x=1\n def f():\n  nonlocal x.y',
            'nonlocal = 1',
            'def o():\n x=1\n def f():\n  nonlocal x\n  x\n  nonlocal x',
            'def o():\n x=1\n def f():\n  nonlocal x\n  x=2\n  nonlocal x',
        ]
        for source in invalid:
            with self.assertRaises(SyntaxError, msg=source):
                compile(source + '\n', '<nonlocal-error>', 'exec')

    def test_static_validation_after_return(self):
        with self.assertRaises(SyntaxError):
            compile('def f():\n return\n nonlocal missing\n', '<unreachable>', 'exec')

    def test_ast_roundtrip(self):
        tree = ast.parse('def outer():\n x=1\n def f():\n  nonlocal x\n  x+=1\n'
                         ' f()\n return x\n')
        declarations = [n for n in ast.walk(tree) if isinstance(n, ast.Nonlocal)]
        self.assertEqual(len(declarations), 1)
        self.assertEqual(list(declarations[0].names), ['x'])
        self.assertEqual(declarations[0].lineno, 4)
        ns = {}
        eval(compile(tree, '<nonlocal-ast>', 'exec'), ns)
        self.assertEqual(ns['outer'](), 2)
        class Declaration(ast.Nonlocal):
            pass
        self.assertEqual(list(Declaration(['x']).names), ['x'])

    def test_interactive(self):
        source = 'def outer():\n x=1\n def f():\n  nonlocal x\n  x+=1'
        self.assertIsNone(codeop.compile_command(source))
        self.assertIsNotNone(codeop.compile_command(source + '\n'))


def test_main():
    from test import test_support
    test_support.run_unittest(NonlocalTest)


if __name__ == '__main__':
    unittest.main()
