"""Native yield-from protocol and generator return values, including PEP 479."""
import ast
import codeop
import sys
import unittest

IS_JYTHON = sys.platform.startswith('java')


def delegate(iterable):
    return (yield from iterable)


def execute(source, namespace=None):
    if namespace is None:
        namespace = {'__name__': __name__}
    eval(compile(source, '<yield-from>', 'exec'), namespace)
    return namespace


class YieldFromTests(unittest.TestCase):
    def exhausted(self, iterator, expected=None):
        with self.assertRaises(StopIteration) as caught:
            next(iterator)
        self.assertIs(caught.exception.value, expected)
        return caught.exception

    def test_builtin_iterables(self):
        for source in ([], [1, None, 2], (1, 2), range(3), 'abc'):
            self.assertEqual(list(delegate(source)), list(source))
        self.exhausted(delegate([]))

    def test_evaluation_and_iter_once(self):
        events = []
        class Source(object):
            def __iter__(self):
                events.append('iter')
                return iter([1, 2])
        def source():
            events.append('source')
            return Source()
        def outer():
            yield from source()
        gen = outer()
        self.assertEqual(events, [])
        self.assertEqual(list(gen), [1, 2])
        self.assertEqual(events, ['source', 'iter'])

    def test_return_identity_and_args(self):
        for marker in (object(), (1, 2), [1, 2], ValueError('marker'), None):
            def inner():
                yield 1
                return marker
            gen = delegate(inner())
            self.assertEqual(next(gen), 1)
            exception = self.exhausted(gen, marker)
            self.assertEqual(exception.args, () if marker is None else (marker,))
            self.exhausted(gen)
            self.assertIsNone(gen.gi_frame)

    def test_return_without_yield_execution(self):
        def inner():
            return 42
            yield
        def outer():
            value = yield from inner()
            yield value
        self.assertEqual(list(outer()), [42])

    def test_nested_delegation(self):
        marker = object()
        def inner():
            yield 1
            return marker
        gen = delegate(delegate(delegate(inner())))
        self.assertEqual(next(gen), 1)
        self.exhausted(gen, marker)

    def test_sequence_protocol(self):
        class Sequence(object):
            def __getitem__(self, index):
                if index == 3:
                    raise IndexError
                return index * 2
        self.assertEqual(list(delegate(Sequence())), [0, 2, 4])

    def test_custom_iterator_stop_value(self):
        marker = object()
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                raise StopIteration(marker)
            next = __next__
        self.exhausted(delegate(Iterator()), marker)

    def test_next_class_lookup(self):
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                raise StopIteration(42)
            next = __next__
        source = Iterator()
        source.__next__ = source.next = lambda: self.fail('instance next must not override slot')
        def outer():
            yield (yield from source)
        self.assertEqual(list(outer()), [42])

    def test_stop_iteration_value_independent_of_args_and_dict(self):
        marker = object()
        stop = StopIteration(marker, 'extra')
        self.assertIs(stop.value, marker)
        stop.args = (99,)
        self.assertIs(stop.value, marker)
        stop.__dict__['value'] = 100
        self.assertIs(stop.value, marker)
        stop.value = 42
        self.assertEqual(stop.args, (99,))
        self.assertEqual(stop.value, 42)
        del stop.value
        self.assertIsNone(stop.value)
        self.assertFalse(hasattr(ValueError(), 'value'))

    def test_stop_subclass_internal_value(self):
        marker = object()
        class Stop(StopIteration):
            @property
            def value(self):
                raise AssertionError('yield-from must use internal stop value')
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                raise Stop(marker)
            next = __next__
        self.exhausted(delegate(Iterator()), marker)

    def test_send_to_subgenerator(self):
        def inner():
            first = yield 'ready'
            second = yield first
            return second
        gen = delegate(inner())
        self.assertEqual(next(gen), 'ready')
        self.assertEqual(gen.send(42), 42)
        marker = object()
        with self.assertRaises(StopIteration) as caught:
            gen.send(marker)
        self.assertIs(caught.exception.value, marker)

    def test_send_none_uses_next_not_send(self):
        events = []
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                events.append('next')
                return 1
            next = __next__
            def send(self, value):
                events.append(value)
                return value
        gen = delegate(Iterator())
        self.assertEqual(next(gen), 1)
        self.assertEqual(gen.send(None), 1)
        self.assertEqual(gen.send(42), 42)
        self.assertEqual(events, ['next', 'next', 42])
        gen.close()

    def test_send_missing_method_is_catchable(self):
        def outer():
            try:
                yield from [1, 2]
            except AttributeError:
                yield 'caught'
        gen = outer()
        self.assertEqual(next(gen), 1)
        self.assertEqual(gen.send(42), 'caught')
        self.exhausted(gen)

    def test_send_return_via_stop(self):
        marker = object()
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            def send(self, value):
                raise StopIteration(value)
        gen = delegate(Iterator())
        next(gen)
        with self.assertRaises(StopIteration) as caught:
            gen.send(marker)
        self.assertIs(caught.exception.value, marker)

    def test_throw_forwarded_to_generator(self):
        error = ValueError('marker')
        def inner():
            try:
                yield 1
            except ValueError as caught:
                self.assertIs(caught, error)
                yield 2
                return 3
        gen = delegate(inner())
        self.assertEqual(next(gen), 1)
        self.assertEqual(gen.throw(error), 2)
        self.assertEqual(self.exhausted(gen, 3).value, 3)

    def test_throw_argument_shape_and_stop(self):
        events = []
        marker = object()
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            def throw(self, *args):
                events.append(args)
                raise StopIteration(marker)
        for args in ((ValueError('marker'),), (ValueError, 'message'), (ValueError, 'message', None)):
            gen = delegate(Iterator())
            next(gen)
            with self.assertRaises(StopIteration) as caught:
                gen.throw(*args)
            self.assertIs(caught.exception.value, marker)
            self.assertEqual(events[-1], args)

    def test_throw_missing_reaches_outer(self):
        marker = ValueError('marker')
        def outer():
            try:
                yield from [1, 2]
            except ValueError as caught:
                yield caught
        gen = outer()
        next(gen)
        self.assertIs(gen.throw(marker), marker)
        self.exhausted(gen)

    def test_injected_stop_iteration_completes_delegate(self):
        marker = object()
        def outer():
            try:
                result = yield from [1, 2]
            except StopIteration:
                self.fail('CPython 3.15 consumes StopIteration at CLEANUP_THROW')
            yield result
        gen = outer()
        next(gen)
        self.assertIs(gen.throw(StopIteration(marker)), marker)
        self.exhausted(gen)

    def test_close_stop_iteration_completes_delegate(self):
        marker = object()
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            def close(self):
                raise StopIteration(marker)
        gen = delegate(Iterator())
        next(gen)
        self.assertIs(gen.close(), marker)
        self.assertIsNone(gen.gi_frame)

    def test_throw_lookup_failure_leaves_delegate_suspended(self):
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            @property
            def throw(self):
                raise RuntimeError('lookup')
        source = Iterator()
        gen = delegate(source)
        next(gen)
        with self.assertRaises(RuntimeError):
            gen.throw(ValueError())
        self.assertIs(gen.gi_yieldfrom, source)
        self.assertEqual(next(gen), 1)
        gen.close()

    def test_close_order_and_no_throw_for_generator_exit(self):
        events = []
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            def throw(self, *args):
                self.fail('GeneratorExit must close, not throw')
            def close(self):
                events.append('inner')
                return 99
        def outer():
            try:
                yield from Iterator()
            finally:
                events.append('outer')
        for action in ('close', 'throw'):
            events[:] = []
            gen = outer()
            next(gen)
            if action == 'close':
                self.assertIsNone(gen.close())
            else:
                with self.assertRaises(GeneratorExit):
                    gen.throw(GeneratorExit())
            self.assertEqual(events, ['inner', 'outer'])
            self.assertIsNone(gen.gi_yieldfrom)
            self.assertIsNone(gen.gi_frame)

    def test_close_error_can_be_caught_by_outer(self):
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            def close(self):
                raise ValueError('close')
        def outer():
            try:
                yield from Iterator()
            except ValueError:
                return 42
        gen = outer()
        next(gen)
        self.assertEqual(gen.close(), 42)
        self.assertIsNone(gen.close())

    def test_ignored_generator_exit(self):
        def inner():
            try:
                yield 1
            except GeneratorExit:
                yield 2
        source = inner()
        gen = delegate(source)
        next(gen)
        with self.assertRaises(RuntimeError):
            gen.close()
        self.assertIsNone(gen.gi_frame)
        source.close()

    def test_close_unstarted_and_exhausted(self):
        events = []
        def inner():
            events.append('started')
            yield 1
        gen = delegate(inner())
        self.assertIsNone(gen.close())
        self.assertEqual(events, [])
        self.exhausted(gen)
        self.assertIsNone(gen.close())

    def test_gi_yieldfrom_lifecycle(self):
        source = iter([1, 2])
        gen = delegate(source)
        self.assertIsNone(gen.gi_yieldfrom)
        self.assertEqual(next(gen), 1)
        self.assertIs(gen.gi_yieldfrom, source)
        self.assertEqual(gen.send(None), 2)
        self.assertIs(gen.gi_yieldfrom, source)
        self.exhausted(gen)
        self.assertIsNone(gen.gi_yieldfrom)
        with self.assertRaises((AttributeError, TypeError)):
            gen.gi_yieldfrom = source

    def test_reentrant_send_throw_close(self):
        for operation in ('send', 'throw', 'close'):
            def inner():
                with self.assertRaises(ValueError):
                    if operation == 'send':
                        gen.send(99)
                    elif operation == 'throw':
                        gen.throw(ValueError('marker'))
                    else:
                        gen.close()
                yield 1
                return 42
            gen = delegate(inner())
            self.assertEqual(next(gen), 1)
            self.exhausted(gen, 42)

    def test_binary_and_pending_call(self):
        def inner():
            yield 1
            return 32
        def outer():
            yield 10 + (yield from inner())
            yield max(5, (yield from inner()))
        self.assertEqual(list(outer()), [1, 42, 1, 32])

    def test_operand_can_suspend(self):
        def outer():
            yield 10 + (yield from (yield 'operand'))
        gen = outer()
        self.assertEqual(next(gen), 'operand')
        def inner():
            yield 1
            return 32
        self.assertEqual(gen.send(inner()), 1)
        self.assertEqual(next(gen), 42)
        self.exhausted(gen)

    def test_augmented_target_survives_delegation(self):
        events = []
        class Box(object):
            value = 10
        box = Box()
        def target():
            events.append('target')
            return box
        def inner():
            yield 'ready'
            return 32
        def outer():
            target().value += (yield from inner())
            yield box.value
        gen = outer()
        self.assertEqual(next(gen), 'ready')
        self.assertEqual(box.value, 10)
        self.assertEqual(next(gen), 42)
        self.assertEqual(events, ['target'])
        self.exhausted(gen)

    def test_return_through_suspending_finally(self):
        marker = object()
        def inner():
            try:
                return marker
            finally:
                yield from [1, 2]
        gen = delegate(inner())
        self.assertEqual(next(gen), 1)
        self.assertEqual(next(gen), 2)
        self.exhausted(gen, marker)

    def test_finally_overrides_return(self):
        def inner():
            try:
                return 1
            finally:
                yield from [2]
                return 3
        gen = delegate(inner())
        self.assertEqual(next(gen), 2)
        self.exhausted(gen, 3)

    def test_exception_state_after_delegate(self):
        error = ValueError('outer')
        def inner():
            yield 1
        def outer():
            try:
                raise error
            except ValueError:
                yield from inner()
                yield sys.exc_info()[1]
        gen = outer()
        self.assertEqual(next(gen), 1)
        self.assertIs(next(gen), error)
        self.exhausted(gen)

    def test_lambda_generator_return(self):
        def inner():
            yield 1
            return 42
        gen = (lambda: (yield from inner()))()
        self.assertEqual(next(gen), 1)
        self.exhausted(gen, 42)

    def test_with_context_unwound(self):
        events = []
        class Manager(object):
            def __enter__(self):
                events.append('enter')
            def __exit__(self, *args):
                events.append(args[0])
        def outer():
            with Manager():
                yield from [1, 2]
        gen = outer()
        next(gen)
        gen.close()
        self.assertEqual(events, ['enter', GeneratorExit])

    def test_invalid_operand_and_iteration_exception(self):
        for source in (None, 42, object()):
            with self.assertRaises(TypeError):
                next(delegate(source))
        class Source(object):
            def __iter__(self):
                raise ValueError('iter')
        with self.assertRaises(ValueError):
            next(delegate(Source()))

    def test_ast_shape_roundtrip_and_subclass(self):
        tree = ast.parse('def f():\n return (yield from source)\n')
        node = tree.body[0].body[0].value
        self.assertIsInstance(node, ast.YieldFrom)
        self.assertEqual(tuple(node._fields), ('value',))
        self.assertIsInstance(node.value.ctx, ast.Load)
        self.assertEqual((node.lineno, node.col_offset), (2, 9))
        class Custom(ast.YieldFrom):
            pass
        replacement = Custom(value=node.value)
        ast.copy_location(replacement, node)
        tree.body[0].body[0].value = replacement
        before = ast.dump(tree)
        ns = {'source': [1, 2]}
        eval(compile(tree, '<ast>', 'exec'), ns)
        self.assertEqual(list(ns['f']()), [1, 2])
        self.assertEqual(ast.dump(tree), before)

    def test_interactive(self):
        with self.assertRaises(SyntaxError):
            codeop.compile_command('def f():\n yield from')
        self.assertIsNone(codeop.compile_command('def f():\n yield from ('))
        code = codeop.compile_command('def f():\n yield from [1, 2]\n')
        self.assertIsNotNone(code)
        ns = {}
        eval(code, ns)
        self.assertEqual(list(ns['f']()), [1, 2])

    def test_throw_constructs_exception_only_at_receiver(self):
        events = []
        class Error(Exception):
            def __init__(self, *args):
                events.append(args)
                Exception.__init__(self, *args)
        def inner():
            try:
                yield 1
            except Error:
                yield 2
        gen = delegate(delegate(inner()))
        next(gen)
        self.assertEqual(gen.throw(Error, 'marker'), 2)
        self.assertEqual(events, [('marker',)])
        gen.close()

    def test_custom_throw_receives_raw_arguments(self):
        events = []
        class Error(Exception):
            def __init__(self):
                self.fail('must not construct for a custom delegate')
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            def throw(self, *args):
                events.append(args)
                return 2
        gen = delegate(Iterator())
        next(gen)
        self.assertEqual(gen.throw(Error), 2)
        self.assertEqual(events, [(Error,)])
        gen.close()

    def test_throw_traceback_identity(self):
        recorded = []
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                return 1
            next = __next__
            def throw(self, *args):
                recorded.append(args)
                return 2
        try:
            raise ValueError('marker')
        except ValueError:
            info = sys.exc_info()
        gen = delegate(Iterator())
        next(gen)
        self.assertEqual(gen.throw(*info), 2)
        self.assertEqual(len(recorded[0]), 3)
        self.assertIs(recorded[0][0], info[0])
        self.assertIs(recorded[0][1], info[1])
        self.assertIs(recorded[0][2], info[2])
        gen.close()

    def test_iteration_failure_clears_delegate(self):
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                raise ValueError('next')
            next = __next__
        def outer():
            try:
                yield from Iterator()
            except ValueError:
                yield 'caught'
        gen = outer()
        self.assertEqual(next(gen), 'caught')
        self.assertIsNone(gen.gi_yieldfrom)
        self.exhausted(gen)

    def test_named_expression_and_dict_stack(self):
        marker = object()
        def inner():
            yield 1
            return marker
        def outer():
            result = {'value': (bound := (yield from inner()))}
            yield result['value'], bound
        gen = outer()
        self.assertEqual(next(gen), 1)
        pair = next(gen)
        self.assertIs(pair[0], marker)
        self.assertIs(pair[1], marker)
        self.exhausted(gen)

    def test_close_returns_caught_generator_exit_value(self):
        marker = object()
        def inner():
            try:
                yield 1
            except GeneratorExit:
                return marker
        gen = inner()
        next(gen)
        self.assertIs(gen.close(), marker)
        self.assertIsNone(gen.close())
        gen = delegate(inner())
        next(gen)
        self.assertIsNone(gen.close())

    def test_start_and_invalid_throw_preserve_state(self):
        gen = delegate([1, 2])
        with self.assertRaises(TypeError):
            gen.send(42)
        self.assertEqual(next(gen), 1)
        with self.assertRaises(TypeError):
            gen.throw(ValueError, None, 'not a traceback')
        self.assertEqual(next(gen), 2)
        self.exhausted(gen)

    def test_syntax_rejections(self):
        for source in ('yield from []', 'class C:\n yield from []',
                       'def f():\n yield from', 'def f():\n yield from 1, 2',
                       'def f():\n (yield from []) = 1', 'def f():\n del (yield from [])'):
            with self.assertRaises(SyntaxError):
                compile(source, '<syntax>', 'exec')



@unittest.skipUnless(IS_JYTHON, 'native JVM and explicit legacy boundaries')
class NativeYieldFromTests(unittest.TestCase):
    def test_comprehension_boundary(self):
        for expression in ('[(yield from source) for x in [1]]',
                           '((yield from source) for x in [1])',
                           '[x for x in (yield from source)]'):
            with self.assertRaises(SyntaxError) as caught:
                compile('def f():\n return ' + expression, '<comprehension>', 'exec')
            self.assertIn('modern comprehension scopes', str(caught.exception))

    def test_close_lookup_failure_reported_unraisable(self):
        from StringIO import StringIO
        class Iterator(object):
            def __iter__(self):
                return self
            def next(self):
                return 1
            @property
            def close(self):
                raise ValueError('close lookup marker')
        gen = delegate(Iterator())
        next(gen)
        stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            self.assertIsNone(gen.close())
            self.assertIn('close lookup marker', sys.stderr.getvalue())
        finally:
            sys.stderr = stderr
        self.assertIsNone(gen.gi_frame)


    def test_java_iterable_identity(self):
        from java.util import ArrayList
        values = ArrayList()
        marker = ArrayList()
        values.add(marker)
        gen = delegate(values)
        self.assertIs(next(gen), marker)
        with self.assertRaises(StopIteration) as caught:
            next(gen)
        self.assertIsNone(caught.exception.value)

    def test_legacy_next_and_explicit_stop(self):
        class Iterator:
            def __iter__(self):
                return self
            def next(self):
                raise StopIteration(42)
        def outer():
            yield (yield from Iterator())
        self.assertEqual(list(outer()), [42])
        def legacy():
            yield 1
            raise StopIteration(42)
        gen = delegate(legacy())
        self.assertEqual(next(gen), 1)
        with self.assertRaises(RuntimeError) as caught:
            next(gen)
        self.assertIsInstance(caught.exception.__cause__, StopIteration)
        self.assertEqual(caught.exception.__cause__.value, 42)

    def test_invalid_ast_operands(self):
        for value in (None, ast.Name(id='x', ctx=ast.Store())):
            tree = ast.parse('def f():\n yield from []\n')
            tree.body[0].body[0].value.value = value
            with self.assertRaises(SyntaxError):
                compile(tree, '<invalid-ast>', 'exec')

    def test_node_locations(self):
        node = ast.YieldFrom(ast.Name(id='x', ctx=ast.Load()), lineno=7, col_offset=3)
        self.assertEqual((node.lineno, node.col_offset), (7, 3))


def test_main():
    from test import test_support
    test_support.run_unittest(YieldFromTests, NativeYieldFromTests)


if __name__ == '__main__':
    unittest.main()
