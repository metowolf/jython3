"""PEP 479 on native generators, compared with exact CPython semantics."""
import __future__
import ast
import contextlib
import sys
import unittest

IS_JYTHON = sys.platform.startswith('java')


def fail_with(error):
    raise error


def delegate(source):
    return (yield from source)


class GeneratorStopTests(unittest.TestCase):
    def converted(self, operation, original=None):
        try:
            operation()
        except RuntimeError as error:
            self.assertEqual(str(error), 'generator raised StopIteration')
            self.assertIsInstance(error.__cause__, StopIteration)
            self.assertIs(error.__context__, error.__cause__)
            self.assertTrue(error.__suppress_context__)
            if original is not None:
                self.assertIs(error.__cause__, original)
            return error
        self.fail('expected PEP 479 RuntimeError')

    def exhausted(self, gen, value=None):
        with self.assertRaises(StopIteration) as caught:
            next(gen)
        self.assertIs(caught.exception.value, value)
        self.assertIsNone(gen.gi_frame)
        self.assertFalse(gen.gi_running)

    def test_explicit_raise_before_first_yield(self):
        original = StopIteration(42)
        def gen():
            raise original
            yield
        iterator = gen()
        self.converted(lambda: next(iterator), original)
        self.exhausted(iterator)

    def test_explicit_raise_after_yield(self):
        original = StopIteration((1, 2))
        def gen():
            yield 1
            raise original
        iterator = gen()
        self.assertEqual(next(iterator), 1)
        self.converted(lambda: next(iterator), original)
        self.exhausted(iterator)
        self.assertIsNone(iterator.close())

    def test_subclass_preserves_identity_without_reconstruction(self):
        calls = []
        class Stop(StopIteration):
            def __init__(self, value):
                calls.append(value)
                StopIteration.__init__(self, value)
            def __str__(self):
                raise AssertionError('must not stringify the cause')
        original = Stop(42)
        def gen():
            raise original
            yield
        self.converted(lambda: next(gen()), original)
        self.assertEqual(calls, [42])

    def test_non_generator_raise_unchanged(self):
        original = StopIteration(42)
        with self.assertRaises(StopIteration) as caught:
            fail_with(original)
        self.assertIs(caught.exception, original)

    def test_other_exceptions_unchanged(self):
        for original in (ValueError('value'), RuntimeError('runtime'), GeneratorExit()):
            def gen():
                raise original
                yield
            with self.assertRaises(type(original)) as caught:
                next(gen())
            self.assertIs(caught.exception, original)

    def test_nested_function_stop(self):
        original = StopIteration('helper')
        def gen():
            yield fail_with(original)
        error = self.converted(lambda: next(gen()), original)
        names = []
        tb = error.__cause__.__traceback__
        while tb is not None:
            names.append(tb.tb_frame.f_code.co_name)
            tb = tb.tb_next
        self.assertIn('gen', names)
        self.assertIn('fail_with', names)

    def test_exhausted_next_is_not_silent_termination(self):
        def gen():
            yield next(iter([]))
        self.converted(lambda: next(gen()))
        self.converted(lambda: next((next(iter([])) for item in [1])))

    def test_generator_expression_filter(self):
        original = StopIteration('filter')
        iterator = (item for item in [1] if fail_with(original))
        self.converted(lambda: next(iterator), original)
        self.exhausted(iterator)

    def test_generator_expression_outer_iter_evaluated_outside(self):
        class Source(object):
            def __iter__(self):
                raise StopIteration('iter')
        with self.assertRaises(StopIteration):
            (item for item in Source())

    def test_caught_stop_is_not_converted(self):
        original = StopIteration(42)
        def gen():
            try:
                raise original
            except StopIteration as error:
                yield error
            return 42
        iterator = gen()
        self.assertIs(next(iterator), original)
        self.exhausted(iterator, 42)

    def test_conversion_is_outside_body_handlers(self):
        original = StopIteration(42)
        events = []
        def gen():
            try:
                raise original
            except RuntimeError:
                events.append('wrong handler')
            finally:
                events.append('finally')
            yield
        self.converted(lambda: next(gen()), original)
        self.assertEqual(events, ['finally'])

    def test_return_values_are_not_converted(self):
        for value in (None, object(), (1, 2), StopIteration(42)):
            def gen():
                yield 1
                return value
            iterator = gen()
            next(iterator)
            self.exhausted(iterator, value)
            self.exhausted(iterator)

    def test_next_default_cannot_hide_error(self):
        def gen():
            raise StopIteration
            yield
        self.converted(lambda: next(gen(), 'default'))
        self.assertEqual(next(iter([]), 'default'), 'default')

    def test_list_cannot_silently_truncate(self):
        def gen():
            yield 1
            raise StopIteration
        self.converted(lambda: list(gen()))

    def test_send_failure(self):
        original = StopIteration(42)
        def gen():
            yield 'ready'
            raise original
        for value in (None, 99):
            iterator = gen()
            next(iterator)
            self.converted(lambda: iterator.send(value), original)
            self.exhausted(iterator)

    def test_throw_into_paused_generator(self):
        original = StopIteration(42)
        def gen():
            yield 1
        iterator = gen()
        next(iterator)
        self.converted(lambda: iterator.throw(original), original)
        self.exhausted(iterator)

    def test_throw_into_unstarted_or_closed_is_not_converted(self):
        events = []
        def gen():
            events.append('started')
            yield 1
        for closed in (False, True):
            iterator = gen()
            if closed:
                iterator.close()
            original = StopIteration(42)
            with self.assertRaises(StopIteration) as caught:
                iterator.throw(original)
            self.assertIs(caught.exception, original)
            self.exhausted(iterator)
        self.assertEqual(events, [])

    def test_throw_can_be_caught_and_return(self):
        original = StopIteration(42)
        def gen():
            try:
                yield 1
            except StopIteration as error:
                return error.value
        iterator = gen()
        next(iterator)
        with self.assertRaises(StopIteration) as caught:
            iterator.throw(original)
        self.assertEqual(caught.exception.value, 42)
        self.assertIsNot(caught.exception, original)

    def test_close_cleanup_stop_is_an_error(self):
        original = StopIteration('cleanup')
        def gen():
            try:
                yield 1
            finally:
                raise original
        iterator = gen()
        next(iterator)
        self.converted(iterator.close, original)
        self.exhausted(iterator)

    def test_close_return_still_delivers_value(self):
        marker = object()
        def gen():
            try:
                yield 1
            except GeneratorExit:
                return marker
        iterator = gen()
        next(iterator)
        self.assertIs(iterator.close(), marker)
        self.assertIsNone(iterator.close())

    def test_pending_stop_survives_yield_in_finally(self):
        original = StopIteration(42)
        def gen():
            try:
                raise original
            finally:
                yield 'cleanup'
        iterator = gen()
        self.assertEqual(next(iterator), 'cleanup')
        self.converted(lambda: next(iterator), original)

    def test_pending_stop_survives_yield_from_in_finally(self):
        original = StopIteration(42)
        def gen():
            try:
                raise original
            finally:
                yield from [1, 2]
        iterator = gen()
        self.assertEqual(next(iterator), 1)
        self.assertEqual(next(iterator), 2)
        self.converted(lambda: next(iterator), original)

    def test_finally_return_suppresses_stop(self):
        def gen():
            try:
                raise StopIteration(1)
            finally:
                return 42
            yield
        self.exhausted(gen(), 42)

    def test_existing_cause_is_preserved(self):
        original = StopIteration('stop')
        cause = ValueError('cause')
        def gen():
            raise original from cause
            yield
        error = self.converted(lambda: next(gen()), original)
        self.assertIs(error.__cause__.__cause__, cause)

    def test_caller_handler_does_not_replace_context(self):
        original = StopIteration('stop')
        outer = ValueError('caller')
        def gen():
            raise original
            yield
        try:
            raise outer
        except ValueError:
            error = self.converted(lambda: next(gen()), original)
            self.assertIs(sys.exc_info()[1], outer)
        self.assertIs(error.__context__, original)
        self.assertIs(original.__context__, outer)

    def test_delegated_generator_error_is_not_return(self):
        original = StopIteration(42)
        def inner():
            yield 1
            raise original
        iterator = delegate(delegate(inner()))
        next(iterator)
        self.converted(lambda: next(iterator), original)
        self.exhausted(iterator)
        self.assertIsNone(iterator.gi_yieldfrom)

    def test_outer_can_catch_delegated_runtime_error(self):
        original = StopIteration(42)
        def inner():
            raise original
            yield
        def outer():
            try:
                yield from inner()
            except RuntimeError as error:
                yield error
        iterator = outer()
        self.assertIs(next(iterator).__cause__, original)
        self.exhausted(iterator)

    def test_delegated_iterator_stop_is_normal(self):
        class Iterator(object):
            def __iter__(self):
                return self
            def __next__(self):
                raise StopIteration(42)
            next = __next__
        self.exhausted(delegate(Iterator()), 42)
        self.exhausted(delegate([]))

    def test_delegated_iter_creation_stop_is_error(self):
        original = StopIteration('iter')
        class Source(object):
            def __iter__(self):
                raise original
        self.converted(lambda: next(delegate(Source())), original)

    def test_throw_into_delegated_generator_is_converted(self):
        original = StopIteration(42)
        def inner():
            yield 1
        iterator = delegate(inner())
        next(iterator)
        self.converted(lambda: iterator.throw(original), original)

    def test_throw_into_iterator_without_throw_completes_delegation(self):
        iterator = delegate([1, 2])
        next(iterator)
        with self.assertRaises(StopIteration) as caught:
            iterator.throw(StopIteration(42))
        self.assertEqual(caught.exception.value, 42)

    def test_contextmanager_body_stop_is_not_wrapped(self):
        events = []
        @contextlib.contextmanager
        def manager():
            try:
                yield
            finally:
                events.append('cleanup')
        original = StopIteration('body')
        with self.assertRaises(StopIteration) as caught:
            with manager():
                raise original
        self.assertIs(caught.exception, original)
        self.assertEqual(events, ['cleanup'])

    def test_contextmanager_can_suppress_stop(self):
        @contextlib.contextmanager
        def manager():
            try:
                yield
            except StopIteration:
                return
        with manager():
            raise StopIteration('body')

    def test_contextmanager_cleanup_stop_is_wrapped(self):
        original = StopIteration('cleanup')
        @contextlib.contextmanager
        def manager():
            yield
            raise original
        def run():
            with manager():
                pass
        self.converted(run, original)

    def test_contextmanager_different_stop_is_not_suppressed(self):
        original = StopIteration('cleanup')
        @contextlib.contextmanager
        def manager():
            try:
                yield
            finally:
                raise original
        def run():
            with manager():
                raise StopIteration('body')
        self.converted(run, original)

    def test_contextmanager_body_runtime_error_identity(self):
        @contextlib.contextmanager
        def manager():
            yield
        original = RuntimeError('body')
        with self.assertRaises(RuntimeError) as caught:
            with manager():
                raise original
        self.assertIs(caught.exception, original)

    def test_contextmanager_setup_stop_is_not_empty_generator(self):
        original = StopIteration('setup')
        @contextlib.contextmanager
        def manager():
            raise original
            yield
        def run():
            with manager():
                self.fail('body must not execute')
        self.converted(run, original)

    def test_runtime_error_from_inner_is_not_wrapped_twice(self):
        original = StopIteration(42)
        errors = []
        def inner():
            raise original
            yield
        def middle():
            try:
                yield from inner()
            except RuntimeError as error:
                errors.append(error)
                raise
        error = self.converted(lambda: next(delegate(middle())), original)
        self.assertIs(error, errors[0])

    def test_difflib_mdiff_terminates_normally(self):
        import difflib
        for context in (None, 0, 1, 3):
            self.assertEqual(list(difflib._mdiff([], [], context)), [])
            rows = list(difflib._mdiff(['a\n', 'b\n'], ['a\n', 'c\n'], context))
            self.assertTrue(any(row[2] for row in rows))
        rows = list(difflib._mdiff(['same\n'], ['same\n']))
        self.assertEqual(rows, [((1, 'same\n'), (1, 'same\n'), False)])
        html = difflib.HtmlDiff().make_table(['a\n'], ['b\n'])
        self.assertIn('diff_sub', html)
        self.assertIn('diff_add', html)

    def test_future_import_and_compile_flags(self):
        flag = __future__.generator_stop.compiler_flag
        self.assertEqual(flag, 0x800000)
        self.assertEqual(__future__.generator_stop.getOptionalRelease(), (3, 5, 0, 'beta', 1))
        self.assertEqual(__future__.generator_stop.getMandatoryRelease(), (3, 7, 0, 'alpha', 0))
        self.assertIn('generator_stop', __future__.all_feature_names)
        body = 'def gen():\n raise StopIteration(42)\n yield\n'
        for source, flags in ((body, 0), (body, flag),
                              ('from __future__ import generator_stop\n' + body, 0)):
            namespace = {}
            code = compile(source, '<generator-stop>', 'exec', flags, True)
            eval(code, namespace)
            self.assertEqual(code.co_flags & flag, flags)
            self.assertEqual(namespace['gen'].__code__.co_flags & flag, flags)
            self.converted(lambda: next(namespace['gen']()))

    def test_compile_flag_inheritance_and_dont_inherit(self):
        flag = __future__.generator_stop.compiler_flag
        source = "def create():\n return (compile('pass', '<inherited>', 'exec'), "
        source += "compile('pass', '<isolated>', 'exec', 0, True))\n"
        namespace = {}
        eval(compile(source, '<flags>', 'exec', flag, True), namespace)
        inherited, isolated = namespace['create']()
        self.assertEqual(inherited.co_flags & flag, flag)
        self.assertEqual(isolated.co_flags & flag, 0)

    def test_future_placement_still_checked(self):
        for source in ('x=1\nfrom __future__ import generator_stop',
                       'def f():\n from __future__ import generator_stop'):
            with self.assertRaises(SyntaxError):
                compile(source, '<future>', 'exec')

    def test_ast_compile_cannot_disable_pep479(self):
        tree = ast.parse('def gen():\n raise StopIteration(42)\n yield\n')
        namespace = {}
        eval(compile(tree, '<ast>', 'exec', 0, True), namespace)
        self.converted(lambda: next(namespace['gen']()))


@unittest.skipUnless(IS_JYTHON, 'native JVM interoperability')
class NativeGeneratorStopTests(unittest.TestCase):
    def test_java_identity_in_stop_value(self):
        from java.util import ArrayList
        marker = ArrayList()
        original = StopIteration(marker)
        def gen():
            raise original
            yield
        with self.assertRaises(RuntimeError) as caught:
            next(gen())
        self.assertIs(caught.exception.__cause__, original)
        self.assertIs(caught.exception.__cause__.value, marker)

    def test_legacy_next_entrypoint(self):
        def gen():
            raise StopIteration(42)
            yield
        with self.assertRaises(RuntimeError) as caught:
            gen().next()
        self.assertEqual(caught.exception.__cause__.value, 42)


def test_main():
    from test import test_support
    test_support.run_unittest(GeneratorStopTests, NativeGeneratorStopTests)


if __name__ == '__main__':
    unittest.main()
