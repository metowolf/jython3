"""Native exception chaining shared with CPython 3 where noted."""
import ast
import codeop
import sys
import traceback
import unittest
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

IS_JYTHON = sys.platform.startswith('java')


def caught(function, *args):
    try:
        function(*args)
    except BaseException as error:
        return error
    raise AssertionError('exception not raised')


def fail(error):
    raise error


def chain(error, cause):
    raise error from cause


class ExceptionChainingTest(unittest.TestCase):
    def test_explicit_instance(self):
        error, cause = ValueError('outer'), KeyError('inner')
        self.assertIs(caught(chain, error, cause), error)
        self.assertIs(error.__cause__, cause)
        self.assertIsNone(error.__context__)
        self.assertTrue(error.__suppress_context__)

    def test_explicit_classes(self):
        error = caught(chain, ValueError, KeyError)
        self.assertIs(type(error), ValueError)
        self.assertIs(type(error.__cause__), KeyError)

    def test_from_none_keeps_context(self):
        original = ValueError('original')
        def function():
            try:
                raise original
            except ValueError:
                raise TypeError('new') from None
        error = caught(function)
        self.assertIsNone(error.__cause__)
        self.assertIs(error.__context__, original)
        self.assertTrue(error.__suppress_context__)

    def test_implicit_context(self):
        original = ValueError('original')
        def function():
            try:
                raise original
            except ValueError:
                1 / 0
        error = caught(function)
        self.assertIs(type(error), ZeroDivisionError)
        self.assertIs(error.__context__, original)
        self.assertFalse(error.__suppress_context__)

    def test_nested_handler_restoration(self):
        original = ValueError('outer')
        def function():
            try:
                raise original
            except ValueError:
                try:
                    raise KeyError('inner')
                except KeyError:
                    pass
                self.assertIs(sys.exc_info()[1], original)
                raise TypeError('last')
        self.assertIs(caught(function).__context__, original)

    def test_handler_does_not_leak(self):
        def function():
            try:
                raise ValueError('finished')
            except ValueError:
                pass
            self.assertIsNone(sys.exc_info()[1])
            raise TypeError('independent')
        self.assertIsNone(caught(function).__context__)

    def test_return_break_continue(self):
        def returning():
            try:
                raise ValueError()
            except ValueError:
                return 3
        self.assertEqual(returning(), 3)
        for mode in ('break', 'continue'):
            for unused in range(2):
                try:
                    raise KeyError()
                except KeyError:
                    if mode == 'break':
                        break
                    continue
            self.assertIsNone(sys.exc_info()[1])
        self.assertIsNone(caught(fail, TypeError()).__context__)

    def test_called_function_inherits_context(self):
        original = ValueError()
        def function():
            try:
                raise original
            except ValueError:
                fail(TypeError())
        self.assertIs(caught(function).__context__, original)

    def test_finally_context(self):
        original = ValueError()
        def function():
            try:
                raise original
            finally:
                self.assertIs(sys.exc_info()[1], original)
                raise TypeError()
        self.assertIs(caught(function).__context__, original)

    def test_finally_return_and_nested_handler(self):
        original = ValueError()
        def function():
            try:
                raise original
            finally:
                try:
                    raise TypeError()
                except TypeError:
                    pass
                self.assertIs(sys.exc_info()[1], original)
                return 4
        self.assertEqual(function(), 4)
        self.assertIsNone(sys.exc_info()[1])

    def test_with_context(self):
        original = ValueError()
        test = self
        class Manager(object):
            def __enter__(self):
                return self
            def __exit__(self, kind, value, tb):
                test.assertIs(value, original)
                test.assertIs(sys.exc_info()[1], original)
                raise TypeError()
        def function():
            with Manager():
                raise original
        self.assertIs(caught(function).__context__, original)

    def test_with_suppression_restores_context(self):
        class Manager(object):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return True
        with Manager():
            raise ValueError()
        self.assertIsNone(sys.exc_info()[1])
        self.assertIsNone(caught(fail, TypeError()).__context__)

    def test_bare_raise(self):
        original = ValueError()
        def function():
            try:
                raise original
            except ValueError:
                raise
        self.assertIs(caught(function), original)
        self.assertIsNone(original.__context__)
        def empty():
            raise
        self.assertIs(type(caught(empty)), RuntimeError)

    def test_reraise_from_called_function(self):
        original = ValueError()
        def reraising():
            raise
        def function():
            try:
                raise original
            except ValueError:
                reraising()
        self.assertIs(caught(function), original)

    def test_generator_handler_state(self):
        original = ValueError()
        def generator():
            try:
                raise original
            except ValueError:
                yield sys.exc_info()[1]
                self.assertIs(sys.exc_info()[1], original)
                raise TypeError()
        iterator = generator()
        self.assertIs(next(iterator), original)
        self.assertIsNone(sys.exc_info()[1])
        try:
            raise KeyError('caller')
        except KeyError:
            error = caught(next, iterator)
        self.assertIs(error.__context__, original)

    def test_generator_throw_context(self):
        original = ValueError('generator')
        def generator():
            try:
                raise original
            except ValueError:
                yield 1
        iterator = generator()
        next(iterator)
        injected = TypeError('injected')
        try:
            raise KeyError('caller')
        except KeyError:
            self.assertIs(caught(iterator.throw, injected), injected)
        self.assertIs(injected.__context__, original)
        self.assertIsNone(original.__context__)

    def test_generator_inherits_current_caller(self):
        def generator():
            yield 1
            raise TypeError()
        iterator = generator()
        try:
            raise ValueError('first caller')
        except ValueError:
            self.assertEqual(next(iterator), 1)
        self.assertIsNone(caught(next, iterator).__context__)
        iterator = generator()
        next(iterator)
        original = KeyError('second caller')
        try:
            raise original
        except KeyError:
            self.assertIs(caught(next, iterator).__context__, original)

    def test_generator_finally_and_close(self):
        original = ValueError()
        seen = []
        def generator():
            try:
                raise original
            finally:
                yield sys.exc_info()[1]
                seen.append(sys.exc_info()[1])
        iterator = generator()
        self.assertIs(next(iterator), original)
        self.assertIs(caught(next, iterator), original)
        self.assertEqual(seen, [original])
        iterator = generator()
        next(iterator)
        iterator.close()
        self.assertIsNone(sys.exc_info()[1])

    def test_raise_expression_yields(self):
        def generator():
            raise (yield 'exception') from (yield 'cause')
        iterator = generator()
        self.assertEqual(next(iterator), 'exception')
        error, cause = ValueError(), KeyError()
        self.assertEqual(iterator.send(error), 'cause')
        self.assertIs(caught(iterator.send, cause), error)
        self.assertIs(error.__cause__, cause)

    def test_evaluation_order(self):
        events = []
        class Error(Exception):
            def __init__(self):
                events.append('construct error')
        class Cause(Exception):
            def __init__(self):
                events.append('construct cause')
        def expression(name, value):
            events.append(name)
            return value
        def function():
            raise expression('error', Error) from expression('cause', Cause)
        caught(function)
        self.assertEqual(events, ['error', 'cause', 'construct error', 'construct cause'])

    def test_invalid_objects(self):
        for cause in (1, 'x', object(), ValueError):
            if cause is ValueError:
                continue
            self.assertIs(type(caught(chain, ValueError(), cause)), TypeError)
        for error in (1, 'x', object()):
            self.assertIs(type(caught(chain, error, None)), TypeError)

    def test_cause_constructor_failure(self):
        original = ValueError()
        class Cause(Exception):
            def __init__(self):
                raise TypeError('construction failed')
        def function():
            try:
                raise original
            except ValueError:
                raise RuntimeError() from Cause
        error = caught(function)
        self.assertIs(type(error), TypeError)
        self.assertIs(error.__context__, original)

    def test_cause_factory_returning_none(self):
        class Cause(Exception):
            def __new__(cls):
                return None
        error = caught(chain, ValueError(), Cause)
        self.assertIs(type(error), ValueError)
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)

    def test_doctest_captures_exception(self):
        import doctest
        sample = ">>> raise ValueError('expected')\nTraceback (most recent call last):\n    ...\nValueError: expected\n"
        test = doctest.DocTestParser().get_doctest(sample, {}, 'chain', '<doctest>', 0)
        runner = doctest.DocTestRunner()
        self.assertEqual(runner.run(test).failed, 0)

    def test_cause_closure_and_ast_validation(self):
        cause = KeyError('closed over')
        def outer():
            local_cause = cause
            def inner():
                raise ValueError() from local_cause
            return inner
        self.assertIs(caught(outer()).__cause__, cause)
        if IS_JYTHON:
            tree = ast.parse('def f():\n return\n raise ValueError from None')
            tree.body[0].body[1].type = None
            self.assertRaises(SyntaxError, compile, tree, '<invalid-cause>', 'exec')

    def test_attributes(self):
        error = ValueError()
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        self.assertIsNone(error.__traceback__)
        self.assertFalse(error.__suppress_context__)
        error.__cause__ = None
        self.assertTrue(error.__suppress_context__)
        error.__suppress_context__ = False
        for name in ('__cause__', '__context__', '__traceback__', '__suppress_context__'):
            self.assertRaises(TypeError, setattr, error, name, 1)
            self.assertRaises((TypeError, AttributeError), delattr, error, name)
        error.__dict__['__cause__'] = 'shadow'
        self.assertIsNone(error.__cause__)
        error.__context__ = error
        self.assertIs(error.__context__, error)

    def test_traceback_and_with_traceback(self):
        error = caught(fail, ValueError())
        tb = error.__traceback__
        self.assertIsNotNone(tb)
        another = TypeError()
        self.assertIs(another.with_traceback(tb), another)
        self.assertIs(another.__traceback__, tb)
        self.assertIs(caught(fail, another), another)
        self.assertGreater(len(traceback.extract_tb(another.__traceback__)),
                           len(traceback.extract_tb(tb)))
        another.__traceback__ = None
        self.assertIsNone(another.__traceback__)
        self.assertRaises(TypeError, another.with_traceback, 1)

    def test_cycle_prevention(self):
        first, second = ValueError(), TypeError()
        def function():
            try:
                raise first
            except ValueError:
                try:
                    raise second
                except TypeError:
                    raise first
        self.assertIs(caught(function), first)
        self.assertIs(first.__context__, second)
        self.assertIsNone(second.__context__)

    def test_format_and_print_chains(self):
        original = caught(fail, KeyError('inner'))
        error = caught(chain, ValueError('outer'), original)
        text = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        self.assertIn('direct cause', text)
        self.assertLess(text.index('KeyError:'), text.index('ValueError:'))
        output = StringIO()
        traceback.print_exception(type(error), error, error.__traceback__, file=output)
        self.assertEqual(output.getvalue(), text)
        plain = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
        self.assertNotIn('direct cause', plain)
        self.assertNotIn('KeyError:', plain)
        error.__cause__ = None
        error.__context__ = original
        self.assertNotIn('KeyError:', ''.join(traceback.format_exception(type(error), error, None)))
        error.__suppress_context__ = False
        self.assertIn('During handling', ''.join(traceback.format_exception(type(error), error, None)))

    def test_manual_cycles_and_long_chains(self):
        first, second = ValueError('first'), TypeError('second')
        first.__cause__, second.__cause__ = second, first
        text = ''.join(traceback.format_exception(type(first), first, None))
        self.assertEqual(text.count('ValueError:'), 1)
        self.assertEqual(text.count('TypeError:'), 1)
        error = ValueError('base')
        for unused in range(1100):
            next_error = ValueError('next')
            next_error.__cause__ = error
            error = next_error
        text = ''.join(traceback.format_exception(type(error), error, None))
        self.assertEqual(text.count('ValueError:'), 1101)

    def test_ast_and_interactive(self):
        tree = ast.parse('raise ValueError() from KeyError()')
        error = caught(eval, compile(tree, '<chain-ast>', 'exec'), {})
        self.assertIs(type(error.__cause__), KeyError)
        self.assertIsInstance(tree.body[0].cause, ast.Call)
        self.assertIsNone(codeop.compile_command('try:\n raise ValueError() from None\n'))
        self.assertIsNotNone(codeop.compile_command('raise ValueError() from None'))
        for source in ('raise from None', 'raise ValueError from',
                       'raise ValueError, 1 from None', 'raise ValueError from None, 1'):
            self.assertRaises(SyntaxError, compile, source, '<invalid-chain>', 'exec')

    @unittest.skipUnless(IS_JYTHON, 'transitional Jython AST and Java integration')
    def test_legacy_ast_and_java_boundary(self):
        old = ast.Raise(ast.Name('ValueError', ast.Load()), None, None)
        self.assertIsNone(old.cause)
        tree = ast.parse('raise ValueError from None')
        tree.body[0].inst = ast.Num(1)
        self.assertRaises(SyntaxError, compile, tree, '<invalid-ast>', 'exec')
        from java.lang import IllegalArgumentException
        self.assertIs(type(caught(chain, ValueError(), IllegalArgumentException())), TypeError)
        java_error = IllegalArgumentException('java')
        try:
            fail(java_error)
        except IllegalArgumentException as error:
            self.assertIs(error, java_error)
        else:
            self.fail('Java exception was not raised')

    @unittest.skipUnless(IS_JYTHON, 'native exception display')
    def test_native_display(self):
        error = caught(chain, ValueError('outer'), KeyError('inner'))
        output = StringIO()
        saved = sys.stderr
        try:
            sys.stderr = output
            sys.__excepthook__(type(error), error, error.__traceback__)
        finally:
            sys.stderr = saved
        self.assertIn('direct cause', output.getvalue())
        error.__cause__.__cause__ = error
        output = StringIO()
        try:
            sys.stderr = output
            sys.__excepthook__(type(error), error, error.__traceback__)
        finally:
            sys.stderr = saved
        self.assertEqual(output.getvalue().count('ValueError:'), 1)


def test_main():
    from test.test_support import run_unittest
    run_unittest(ExceptionChainingTest)


if __name__ == '__main__':
    unittest.main()
