"""PEP 465 on the native JVM, compared with CPython 3.15.2."""
import ast
import codeop
import io
import operator
import sys
import tokenize
import unittest

IS_JYTHON = sys.platform.startswith('java')


def execute(source, namespace=None):
    if namespace is None:
        namespace = {'__name__': __name__}
    eval(compile(source, '<matmul>', 'exec'), namespace)
    return namespace


class Matrix(object):
    def __init__(self, value):
        self.value = value

    def __matmul__(self, other):
        return Matrix((self.value, other.value))


class MatmulTests(unittest.TestCase):
    def test_basic_and_left_associativity(self):
        a, b, c = Matrix('a'), Matrix('b'), Matrix('c')
        self.assertEqual((a @ b @ c).value, (('a', 'b'), 'c'))
        self.assertEqual((a @ (b @ c)).value, ('a', ('b', 'c')))

    def test_arbitrary_result_and_identity(self):
        for result in (None, False, 0, 'answer', object()):
            class Left(object):
                def __matmul__(self, other):
                    return result
            self.assertIs(Left() @ object(), result)

    def test_reflected_fallback(self):
        events = []
        class Left(object):
            def __matmul__(self, other):
                events.append('left')
                return NotImplemented
        class Right(object):
            def __rmatmul__(self, other):
                events.append('right')
                return other
        left = Left()
        self.assertIs(left @ Right(), left)
        self.assertEqual(events, ['left', 'right'])

    def test_missing_forward(self):
        class Right(object):
            def __rmatmul__(self, other):
                return other
        left = object()
        self.assertIs(left @ Right(), left)

    def test_same_type_never_reflects(self):
        events = []
        class Same(object):
            def __matmul__(self, other):
                events.append('left')
                return NotImplemented
            def __rmatmul__(self, other):
                events.append('wrong')
                return 1
        with self.assertRaises(TypeError):
            Same() @ Same()
        self.assertEqual(events, ['left'])

    def test_same_type_reflected_only(self):
        class Same(object):
            def __rmatmul__(self, other):
                return 1
        with self.assertRaises(TypeError):
            Same() @ Same()

    def test_subclass_reflected_priority(self):
        events = []
        class Base(object):
            def __matmul__(self, other):
                events.append('base')
                return 1
        class Sub(Base):
            def __rmatmul__(self, other):
                events.append('sub')
                return 2
        self.assertEqual(Base() @ Sub(), 2)
        self.assertEqual(events, ['sub'])

    def test_inherited_reflected_not_prioritized(self):
        events = []
        class Base(object):
            def __matmul__(self, other):
                events.append('forward')
                return 1
            def __rmatmul__(self, other):
                events.append('reverse')
                return 2
        class Sub(Base):
            pass
        self.assertEqual(Base() @ Sub(), 1)
        Sub.__rmatmul__ = Base.__rmatmul__
        self.assertEqual(Base() @ Sub(), 1)
        self.assertEqual(events, ['forward', 'forward'])

    def test_prioritized_reflected_not_repeated(self):
        events = []
        class Base(object):
            def __matmul__(self, other):
                events.append('forward')
                return NotImplemented
        class Sub(Base):
            def __rmatmul__(self, other):
                events.append('reverse')
                return NotImplemented
        with self.assertRaises(TypeError):
            Base() @ Sub()
        self.assertEqual(events, ['reverse', 'forward'])

    def test_inplace_identity(self):
        class Mutable(Matrix):
            def __imatmul__(self, other):
                self.value += other.value
                return self
        value = original = Mutable(3)
        value @= Matrix(4)
        self.assertIs(value, original)
        self.assertEqual(value.value, 7)

    def test_inplace_replacement(self):
        replacement = object()
        class Left(object):
            def __imatmul__(self, other):
                return replacement
        left = Left()
        left @= 1
        self.assertIs(left, replacement)

    def test_inplace_missing_falls_back(self):
        value = Matrix(1)
        original = value
        value @= Matrix(2)
        self.assertIsNot(value, original)
        self.assertEqual(value.value, (1, 2))

    def test_inplace_notimplemented_full_binary_protocol(self):
        events = []
        class Base(object):
            def __imatmul__(self, other):
                events.append('inplace')
                return NotImplemented
            def __matmul__(self, other):
                events.append('forward')
                return 1
        class Sub(Base):
            def __rmatmul__(self, other):
                events.append('reverse')
                return 2
        value = Base()
        value @= Sub()
        self.assertEqual(value, 2)
        self.assertEqual(events, ['inplace', 'reverse'])

    def test_failures_and_symbols(self):
        for source, symbol in (('a @ b', '@'), ('a @= b', '@=')):
            for a, b in ((1, 2), ([], []), (object(), object())):
                with self.assertRaises(TypeError) as caught:
                    execute(source, {'a': a, 'b': b})
                self.assertIn('for ' + symbol + ':', str(caught.exception))

    def test_exceptions_do_not_fallback(self):
        for method in ('__matmul__', '__rmatmul__', '__imatmul__'):
            events = []
            def fail(self, other):
                events.append('fail')
                raise ValueError('marker')
            def fallback(self, other):
                events.append('wrong')
                return 1
            Left = type('Left', (object,), {'__matmul__': fail if method == '__matmul__' else fallback})
            Right = type('Right', (Left,), {'__rmatmul__': fail if method == '__rmatmul__' else fallback})
            if method == '__imatmul__':
                Left.__imatmul__ = fail
            source = 'left @= right' if method == '__imatmul__' else 'left @ right'
            right = object() if method == '__matmul__' else Right()
            with self.assertRaises(ValueError):
                execute(source, {'left': Left(), 'right': right})
            self.assertEqual(events, ['fail'])

    def test_special_lookup_ignores_instance(self):
        value = Matrix(1)
        value.__matmul__ = lambda other: 'wrong'
        self.assertEqual((value @ Matrix(2)).value, (1, 2))
        class Empty(object):
            pass
        empty = Empty()
        empty.__matmul__ = lambda other: 42
        with self.assertRaises(TypeError):
            empty @ 1

    def test_descriptor_binding(self):
        events = []
        class Descriptor(object):
            def __get__(self, instance, owner):
                events.append((instance, owner))
                return lambda other: other
        class Left(object):
            __matmul__ = Descriptor()
        left, right = Left(), object()
        self.assertIs(left @ right, right)
        self.assertEqual(events, [(left, Left)])

    def test_static_and_class_methods(self):
        class Static(object):
            __matmul__ = staticmethod(lambda other: other)
        class Class(object):
            __matmul__ = classmethod(lambda cls, other: cls)
        right = object()
        self.assertIs(Static() @ right, right)
        self.assertIs(Class() @ right, Class)

    def test_noncallable_special_method(self):
        class Left(object):
            __matmul__ = None
        with self.assertRaises(TypeError):
            Left() @ 1

    def test_dynamic_type_update(self):
        class Left(object):
            pass
        left = Left()
        with self.assertRaises(TypeError):
            left @ 1
        Left.__matmul__ = lambda self, other: other + 1
        self.assertEqual(left @ 1, 2)
        Left.__matmul__ = lambda self, other: other + 2
        self.assertEqual(left @ 1, 3)
        del Left.__matmul__
        with self.assertRaises(TypeError):
            left @ 1

    def test_operand_evaluation_order(self):
        events = []
        def operand(name):
            events.append(name)
            return Matrix(name)
        self.assertEqual((operand('left') @ operand('right')).value, ('left', 'right'))
        self.assertEqual(events, ['left', 'right'])

    def test_precedence_ast(self):
        for symbol, cls in (('*', ast.Mult), ('/', ast.Div), ('//', ast.FloorDiv), ('%', ast.Mod)):
            first = ast.parse('a @ b ' + symbol + ' c', mode='eval').body
            second = ast.parse('a ' + symbol + ' b @ c', mode='eval').body
            self.assertIsInstance(first.op, cls)
            self.assertIsInstance(first.left.op, ast.MatMult)
            self.assertIsInstance(second.op, ast.MatMult)
            self.assertIsInstance(second.left.op, cls)
        plus = ast.parse('a + b @ c ** -d', mode='eval').body
        self.assertIsInstance(plus.op, ast.Add)
        self.assertIsInstance(plus.right.op, ast.MatMult)
        self.assertIsInstance(plus.right.right.op, ast.Pow)
        unary = ast.parse('-a @ b', mode='eval').body
        self.assertIsInstance(unary.left, ast.UnaryOp)

    def test_attribute_target_evaluated_once(self):
        events = []
        class Box(object):
            def get(self):
                events.append('get')
                return Matrix(1)
            def put(self, value):
                events.append(('set', value.value))
            value = property(get, put)
        box = Box()
        def target():
            events.append('target')
            return box
        def rhs():
            events.append('rhs')
            return Matrix(2)
        target().value @= rhs()
        self.assertEqual(events, ['target', 'get', 'rhs', ('set', (1, 2))])

    def test_subscript_and_slice_target_once(self):
        for source in ('target()[key()] @= rhs()', 'target()[key():3] @= rhs()'):
            events = []
            class Box(object):
                def __getitem__(self, key):
                    events.append(('get', key))
                    return Matrix(1)
                def __setitem__(self, key, value):
                    events.append(('set', key, value.value))
            box = Box()
            def target():
                events.append('target')
                return box
            def key():
                events.append('key')
                return 1
            def rhs():
                events.append('rhs')
                return Matrix(2)
            execute(source, locals())
            self.assertEqual([x[0] if isinstance(x, tuple) else x for x in events],
                             ['target', 'key', 'get', 'rhs', 'set'])
            self.assertEqual(events[2][1], events[4][1])
            self.assertEqual(events[4][2], (1, 2))

    def test_failure_does_not_write_back(self):
        events = []
        class Box(object):
            def __getitem__(self, key):
                return object()
            def __setitem__(self, key, value):
                events.append('wrong')
        with self.assertRaises(TypeError):
            Box()[0] @= 1
        self.assertEqual(events, [])
        namespace = {'value': object()}
        original = namespace['value']
        with self.assertRaises(TypeError):
            execute('value @= 1', namespace)
        self.assertIs(namespace['value'], original)

    def test_nonlocal_and_global(self):
        ns = execute('value = Matrix(1)\ndef f():\n global value\n value @= Matrix(2)\nf()', {'Matrix': Matrix})
        self.assertEqual(ns['value'].value, (1, 2))
        def outer():
            value = Matrix(1)
            def inner():
                nonlocal value
                value @= Matrix(2)
            inner()
            return value
        self.assertEqual(outer().value, (1, 2))

    def test_generators_both_operands(self):
        def gen():
            value = (yield 'left') @ (yield 'right')
            yield value
        iterator = gen()
        self.assertEqual(next(iterator), 'left')
        self.assertEqual(iterator.send(Matrix(1)), 'right')
        self.assertEqual(iterator.send(Matrix(2)).value, (1, 2))
        iterator.close()

    def test_generator_augmented_targets(self):
        for source in ('value @= (yield 1)\n yield value',
                       'box.value @= (yield 1)\n yield box.value',
                       'items[0] @= (yield 1)\n yield items[0]'):
            class Box(object):
                pass
            box = Box()
            box.value = Matrix(1)
            ns = {'value': Matrix(1), 'box': box, 'items': [Matrix(1)]}
            execute('def gen(value=value):\n ' + source + '\niterator = gen()', ns)
            iterator = ns['iterator']
            self.assertEqual(next(iterator), 1)
            self.assertEqual(iterator.send(Matrix(2)).value, (1, 2))
            iterator.close()

    def test_generator_throw_and_close(self):
        events = []
        class Left(object):
            def __matmul__(self, other):
                events.append('wrong')
        def gen():
            try:
                Left() @ (yield 1)
            finally:
                events.append('done')
        iterator = gen()
        next(iterator)
        with self.assertRaises(ValueError):
            iterator.throw(ValueError('marker'))
        iterator = gen()
        next(iterator)
        iterator.close()
        self.assertEqual(events, ['done', 'done'])

    def test_ast_roundtrip_and_positions(self):
        tree = ast.parse('result = a @ b\na @= b\n')
        binary = tree.body[0].value
        self.assertIsInstance(binary.op, ast.MatMult)
        self.assertEqual((binary.lineno, binary.col_offset), (1, 9))
        self.assertIsInstance(tree.body[1].op, ast.MatMult)
        ns = {'a': Matrix(1), 'b': Matrix(2)}
        eval(compile(tree, '<ast>', 'exec'), ns)
        self.assertEqual(ns['result'].value, (1, 2))
        self.assertEqual(ns['a'].value, (1, 2))
        self.assertEqual(tuple(ast.MatMult()._fields), ())

    def test_manual_store_ast_not_mutated(self):
        for source in ('a @= b', 'box.a @= b', 'items[0] @= b'):
            class Box(object):
                pass
            box = Box()
            box.a = Matrix(1)
            ns = {'a': Matrix(1), 'b': Matrix(2), 'box': box, 'items': [Matrix(1)]}
            tree = ast.parse(source)
            target = tree.body[0].target
            target.ctx = ast.Store()
            before = ast.dump(tree)
            code = compile(tree, '<manual-ast>', 'exec')
            self.assertIs(tree.body[0].target, target)
            self.assertEqual(ast.dump(tree), before)
            eval(code, ns)
            result = ns['a'] if source.startswith('a ') else box.a if source.startswith('box') else ns['items'][0]
            self.assertEqual(result.value, (1, 2))

    def test_ast_operator_subclass(self):
        class Custom(ast.MatMult):
            pass
        op = Custom()
        op.marker = 42
        tree = ast.parse('a @ b', mode='eval')
        tree.body.op = op
        self.assertEqual(eval(compile(tree, '<custom-op>', 'eval'), {'a': Matrix(1), 'b': Matrix(2)}).value, (1, 2))
        self.assertEqual(op.marker, 42)

    def test_interactive_input(self):
        self.assertIsNone(codeop.compile_command('a @ ('))
        self.assertIsNone(codeop.compile_command('a @= ('))
        self.assertIsNone(codeop.compile_command('@a @ b\ndef f():'))
        self.assertIsNotNone(codeop.compile_command('a @ b'))
        self.assertIsNotNone(codeop.compile_command('a @= b'))
        for source in ('a @', '@=a', 'a @ @ b', 'a @= b @= c', 'f() @= b'):
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid>', 'exec')

    def test_tokenize_roundtrip(self):
        source = u'a @ b\na @= b\n@a\ndef f(): pass\n'
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        ops = [item[1] for item in tokens if item[0] == tokenize.OP]
        self.assertEqual([op for op in ops if op.startswith('@')], ['@', '@=', '@'])
        self.assertEqual(tokenize.untokenize(tokens), source)

    def test_operator_module(self):
        a, b = Matrix(1), Matrix(2)
        for name in ('matmul', '__matmul__', 'imatmul', '__imatmul__'):
            method = getattr(operator, name)
            self.assertEqual(method(a, b).value, (1, 2))
            for args in ((), (a,), (a, b, a)):
                with self.assertRaises(TypeError):
                    method(*args)

    def test_reflected_staticmethod_alias(self):
        reverse = lambda other: 'reverse'
        class Base(object):
            __rmatmul__ = staticmethod(reverse)
            def __matmul__(self, other):
                return 'forward'
        class Sub(Base):
            __rmatmul__ = staticmethod(reverse)
        self.assertEqual(Base() @ Sub(), 'forward')

    def test_inherited_reflected_classmethod(self):
        class Base(object):
            def __matmul__(self, other):
                return 'forward'
            @classmethod
            def __rmatmul__(cls, other):
                return cls
        class Sub(Base):
            pass
        self.assertIs(Base() @ Sub(), Sub)

    def test_reflected_descriptor_comparison(self):
        events = []
        class Method(object):
            def __ne__(self, other):
                events.append('compare')
                return False
            def __call__(self, other):
                return 'reverse'
        class Descriptor(object):
            def __get__(self, instance, owner):
                events.append(owner.__name__)
                return Method()
        class Base(object):
            __rmatmul__ = Descriptor()
            def __matmul__(self, other):
                events.append('forward')
                return 'forward'
        class Sub(Base):
            pass
        self.assertEqual(Base() @ Sub(), 'forward')
        self.assertEqual(events, ['Sub', 'Base', 'compare', 'forward'])

    def test_reflected_descriptor_failure(self):
        class Descriptor(object):
            def __get__(self, instance, owner):
                raise ValueError('descriptor')
        class Base(object):
            def __matmul__(self, other):
                return 'wrong'
        class Sub(Base):
            __rmatmul__ = Descriptor()
        with self.assertRaises(ValueError):
            Base() @ Sub()

    def test_matrix_decorator_expression(self):
        class Factory(object):
            def __matmul__(self, other):
                return lambda function: function
        ns = execute('@factory @ other\ndef f(): return 42', {'factory': Factory(), 'other': object()})
        self.assertEqual(ns['f'](), 42)


@unittest.skipUnless(IS_JYTHON, 'native JVM AST and legacy interoperability')
class NativeMatmulTests(unittest.TestCase):
    def test_legacy_classes_without_coercion(self):
        ns = execute('class Left:\n def __matmul__(self, other): return NotImplemented\n def __coerce__(self, other): raise AssertionError("coerce")\nclass Right:\n def __rmatmul__(self, other): return 42\nresult = Left() @ Right()')
        self.assertEqual(ns['result'], 42)

    def test_invalid_ast_contexts(self):
        for side in ('left', 'right'):
            tree = ast.parse('a @ b', mode='eval')
            getattr(tree.body, side).ctx = ast.Store()
            with self.assertRaises(SyntaxError):
                compile(tree, '<bad-context>', 'eval')
        for target in (ast.Name(id='a', ctx=ast.Load()), ast.Num(n=1)):
            tree = ast.parse('a @= b')
            tree.body[0].target = ast.copy_location(target, tree.body[0].target)
            with self.assertRaises(SyntaxError):
                compile(tree, '<bad-target>', 'exec')

    def test_missing_ast_operand(self):
        for side in ('left', 'right'):
            tree = ast.parse('a @ b', mode='eval')
            setattr(tree.body, side, None)
            with self.assertRaises(SyntaxError):
                compile(tree, '<missing>', 'eval')

    def test_stable_ast_and_token_numbers(self):
        import token
        self.assertEqual((int(ast.Mult()), int(ast.FloorDiv()), int(ast.MatMult())), (3, 12, 13))
        self.assertEqual((token.AT, token.OP, token.ERRORTOKEN, token.ATEQUAL), (50, 51, 52, 53))

    def test_java_subclass(self):
        from java.util import ArrayList
        class Values(ArrayList):
            def __matmul__(self, other):
                return self.get(0) + other
        values = Values()
        values.add(40)
        self.assertEqual(values @ 2, 42)


def test_main():
    from test import test_support
    test_support.run_unittest(MatmulTests, NativeMatmulTests)


if __name__ == '__main__':
    unittest.main()
