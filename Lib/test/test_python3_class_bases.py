"""Native iterable class bases; shared checks also run on CPython 3.15.2."""
import ast
import codeop
import sys
import unittest

IS_JYTHON = sys.platform.startswith('java')


class A(object):
    def first(self):
        return 'A'


class B(object):
    def second(self):
        return 'B'


class D(object):
    pass


def execute(source, namespace=None):
    if namespace is None:
        namespace = {'A': A, 'B': B, 'D': D, '__name__': __name__}
    eval(compile(source, '<class-bases>', 'exec'), namespace)
    return namespace


class ClassBasesTests(unittest.TestCase):
    def test_single_iterable(self):
        for bases in ([A], (A,), iter([A]), (base for base in [A])):
            class C(*bases):
                pass
            self.assertEqual(C.__bases__, (A,))
            self.assertEqual(C().first(), 'A')

    def test_empty_operands(self):
        class C(*[], *(), object, *iter([]),):
            pass
        self.assertEqual(C.__bases__, (object,))

    def test_multiple_stars(self):
        class C(*[A], *(B,), *[D]):
            pass
        self.assertEqual(C.__bases__, (A, B, D))
        self.assertEqual(C.__mro__, (C, A, B, D, object))
        self.assertEqual((C().first(), C().second()), ('A', 'B'))

    def test_mixed_bases(self):
        class C(A, *[B], D, *[]):
            pass
        self.assertEqual(C.__bases__, (A, B, D))

    def test_conditional_and_lambda_operands(self):
        class C(*[A] if True else [B], *(lambda: [B])()):
            pass
        self.assertEqual(C.__bases__, (A, B))
        tree = ast.parse('class C(*lambda: [A]): pass')
        self.assertIsInstance(tree.body[0].bases[0].value, ast.Lambda)
        with self.assertRaises(TypeError):
            execute('class C(*lambda: [A]): pass')

    def test_nested_displays_and_calls(self):
        def bases(*items):
            return items
        class C(*bases(*[A], *[B]), *[*[D]]):
            pass
        self.assertEqual(C.__bases__, (A, B, D))

    def test_generator_and_comprehension(self):
        class C(*(base for base in [A]), *[base for base in [B]]):
            pass
        self.assertEqual(C.__bases__, (A, B))

    def test_consumption_order(self):
        events = []
        def iterable():
            events.append('start')
            yield A
            events.append('end')
        def mark(label, value):
            events.append(label)
            return value
        class C(*mark('star', iterable()), mark('normal', B), *mark('last', [D])):
            events.append('body')
        self.assertEqual(C.__bases__, (A, B, D))
        self.assertEqual(events, ['star', 'start', 'end', 'normal', 'last', 'body'])

    def test_iter_called_once(self):
        events = []
        class Iterable(object):
            def __iter__(self):
                events.append('iter')
                return iter([A])
        class C(*Iterable()):
            pass
        self.assertEqual(events, ['iter'])
        self.assertEqual(C.__bases__, (A,))

    def test_sequence_protocol(self):
        class Sequence(object):
            def __getitem__(self, index):
                if index == 2:
                    raise IndexError(index)
                return (A, B)[index]
        class C(*Sequence()):
            pass
        self.assertEqual(C.__bases__, (A, B))

    def test_iterator_protocol(self):
        class Iterator(object):
            def __init__(self):
                self.used = False
            def __iter__(self):
                return self
            def __next__(self):
                if self.used:
                    raise StopIteration
                self.used = True
                return A
            next = __next__
        class C(*Iterator()):
            pass
        self.assertEqual(C.__bases__, (A,))

    def test_mapping_iterates_keys(self):
        class C(*{A: 'unused'}):
            pass
        self.assertEqual(C.__bases__, (A,))

    def test_non_iterable(self):
        for value in (None, 1, A):
            with self.assertRaises(TypeError):
                class C(*value):
                    pass

    def test_iterator_typeerror_preserved(self):
        class Broken(object):
            def __iter__(self):
                raise TypeError('inside base iterator')
        with self.assertRaises(TypeError) as caught:
            class C(*Broken()):
                pass
        self.assertEqual(str(caught.exception), 'inside base iterator')

    def test_iteration_error_stops_later_base_and_body(self):
        events = []
        def broken():
            yield A
            raise RuntimeError('broken base')
        def later():
            events.append('unexpected')
            return B
        with self.assertRaises(RuntimeError):
            class C(*broken(), later()):
                events.append('unexpected body')
        self.assertEqual(events, [])

    def test_sources_not_mutated(self):
        bases = [A, B]
        class C(*bases):
            pass
        bases[:] = []
        self.assertEqual(C.__bases__, (A, B))
        saved = (A, B)
        class E(*saved):
            pass
        self.assertEqual(saved, (A, B))
        self.assertEqual(E.__bases__, saved)

    def test_duplicate_base(self):
        with self.assertRaises(TypeError):
            class C(*[A], *[A]):
                pass

    def test_mro_conflict(self):
        class X(A, B):
            pass
        class Y(B, A):
            pass
        with self.assertRaises(TypeError):
            class C(*[X], *[Y]):
                pass

    def test_parenthesized_tuple_is_one_base(self):
        for source in ('class C((A, B)): pass', 'class C((A,)): pass',
                       'class C(()): pass', 'class C(*[], (A, B)): pass'):
            tree = ast.parse(source)
            self.assertIsInstance(tree.body[0].bases[-1], ast.Tuple)
            with self.assertRaises(TypeError):
                execute(source)
        class C(*(A, B)):
            pass
        self.assertEqual(C.__bases__, (A, B))

    def test_failed_definition_preserves_binding(self):
        marker = object()
        namespace = {'C': marker}
        with self.assertRaises(TypeError):
            execute('class C(*None): pass', namespace)
        self.assertIs(namespace['C'], marker)

    def test_decorators_evaluated_before_bases(self):
        for header in ('*[A], *[B]', 'A, B'):
            events = []
            def decorate(label):
                events.append('eval ' + label)
                def apply(cls):
                    events.append('apply ' + label)
                    return cls
                return apply
            def bases():
                events.append('bases')
                return [A, B]
            source = ('@decorate("outer")\n@decorate("inner")\n'
                      'class C(%s):\n events.append("body")')
            namespace = {'A': A, 'B': B, 'events': events, 'decorate': decorate,
                         'bases': bases, '__name__': __name__}
            execute(source % header, namespace)
            self.assertEqual(events, ['eval outer', 'eval inner', 'body',
                                      'apply inner', 'apply outer'])
            events[:] = []
            execute(source % '*bases()', namespace)
            self.assertEqual(events, ['eval outer', 'eval inner', 'bases', 'body',
                                      'apply inner', 'apply outer'])

    def test_decorator_failure_precedes_bases(self):
        events = []
        def decorate():
            raise RuntimeError('decorator failed')
        def bases():
            events.append('unexpected')
            return [A]
        with self.assertRaises(RuntimeError):
            @decorate()
            class C(*bases()):
                events.append('unexpected body')
        self.assertEqual(events, [])

    def test_decorator_application_failure_preserves_binding(self):
        events = []
        marker = object()
        def decorate(cls):
            events.append('apply')
            raise RuntimeError('application failed')
        namespace = {'C': marker, 'A': A, 'decorate': decorate,
                     'events': events, '__name__': __name__}
        with self.assertRaises(RuntimeError):
            execute('@decorate\nclass C(*[A]):\n events.append("body")', namespace)
        self.assertEqual(events, ['body', 'apply'])
        self.assertIs(namespace['C'], marker)

    def test_body_failure_does_not_apply_decorator(self):
        events = []
        def decorate():
            events.append('evaluate')
            def apply(cls):
                events.append('unexpected')
            return apply
        with self.assertRaises(RuntimeError):
            @decorate()
            class C(*[A]):
                raise RuntimeError('body failed')
        self.assertEqual(events, ['evaluate'])

    def test_decorator_can_replace_class(self):
        marker = object()
        def replace(cls):
            self.assertEqual(cls.__bases__, (A, B))
            return marker
        @replace
        class C(*[A], *[B]):
            pass
        self.assertIs(C, marker)

    def test_outer_scope_and_method_closure(self):
        def outer():
            bases = [A]
            tag = object()
            class C(*bases):
                bases = 'class attribute'
                def value(self):
                    return tag
            return C, tag
        cls, tag = outer()
        self.assertEqual(cls.__bases__, (A,))
        self.assertEqual(cls.bases, 'class attribute')
        self.assertIs(cls().value(), tag)

    def test_class_header_in_class_scope(self):
        class Outer(object):
            bases = [A]
            class Inner(*bases):
                pass
        self.assertEqual(Outer.Inner.__bases__, (A,))

    def test_nonlocal_class_binding(self):
        C = None
        def define():
            nonlocal C
            class C(*[A]):
                pass
        define()
        self.assertEqual(C.__bases__, (A,))

    def test_inherited_metaclass_and_saved_bases(self):
        events = []
        class Meta(type):
            def __new__(meta, name, bases, namespace):
                events.append((name, bases))
                return type.__new__(meta, name, bases, namespace)
        Base = Meta('Base', (object,), {})
        class C(*[Base], *[]):
            pass
        self.assertIs(type(C), Meta)
        self.assertEqual(events[-1], ('C', (Base,)))
        self.assertEqual(C.__bases__, (Base,))

    def test_shadowed_builtins(self):
        namespace = {'A': A, 'list': None, 'tuple': None, 'iter': None,
                     '__name__': __name__}
        execute('class C(*[A], *[]): pass', namespace)
        self.assertEqual(namespace['C'].__bases__, (A,))

    def test_generator_suspension(self):
        events = []
        def decorate(label):
            events.append(label)
            def apply(cls):
                events.append('apply')
                return cls
            return apply
        def gen():
            @decorate((yield 'decorator'))
            class C(*(yield 'first'), (yield 'normal'), *(yield 'last')):
                events.append('body')
            yield C
        iterator = gen()
        self.assertEqual(next(iterator), 'decorator')
        self.assertEqual(iterator.send('evaluate'), 'first')
        self.assertEqual(iterator.send([A]), 'normal')
        self.assertEqual(iterator.send(B), 'last')
        self.assertEqual(events, ['evaluate'])
        cls = iterator.send([D])
        self.assertEqual(cls.__bases__, (A, B, D))
        self.assertEqual(events, ['evaluate', 'body', 'apply'])
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_generator_nested_star_expression(self):
        def gen():
            class C(*[*(yield 'bases')], *[]):
                pass
            yield C
        iterator = gen()
        self.assertEqual(next(iterator), 'bases')
        self.assertEqual(iterator.send([A, B]).__bases__, (A, B))
        iterator.close()

    def test_generator_close_and_throw(self):
        events = []
        def gen():
            try:
                class C(*[A], *(yield 'pause')):
                    events.append('unexpected body')
                yield C
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

    def test_ast_roundtrip(self):
        source = 'class C(A, *[B], *[D]): pass'
        tree = ast.parse(source)
        self.assertIsInstance(tree.body[0].bases[1], ast.Starred)
        self.assertIsInstance(tree.body[0].bases[1].ctx, ast.Load)
        self.assertEqual(tree.body[0].bases[1].col_offset, source.index('*'))
        namespace = {'A': A, 'B': B, 'D': D, '__name__': __name__}
        eval(compile(tree, '<class-ast>', 'exec'), namespace)
        self.assertEqual(namespace['C'].__bases__, (A, B, D))

    def test_interactive_input(self):
        for source in ('class C(*', 'class C(*a, *', 'class C(*a):',
                       '@decorate()\nclass C(*a):'):
            self.assertIsNone(codeop.compile_command(source))
        self.assertIsNotNone(codeop.compile_command('class C(*a, *b):\n pass\n'))

    def test_invalid_syntax(self):
        for source in ('class C(*): pass', 'class C(*a, , B): pass',
                       'class C(*a for a in []): pass', 'class C(x for x in []): pass',
                       'class C(*a b): pass', 'class C(*(yield 1)): pass',
                       'class C(*a):\n yield 1'):
            with self.assertRaises(SyntaxError):
                compile(source, '<invalid-class>', 'exec')

    def test_many_empty_expansions(self):
        source = 'class C(' + ', '.join(['*[]'] * 80 + ['A']) + '): pass'
        self.assertEqual(execute(source)['C'].__bases__, (A,))


@unittest.skipUnless(IS_JYTHON, 'native JVM AST and Java integration')
class NativeClassBasesTests(unittest.TestCase):
    def test_java_iterable_of_python_bases(self):
        from java.util import ArrayList
        bases = ArrayList()
        bases.add(A)
        bases.add(B)
        class C(*bases):
            pass
        self.assertEqual(C.__bases__, (A, B))
        self.assertEqual(bases.size(), 2)

    def test_java_class_inheritance(self):
        from java.util import ArrayList
        class C(*[ArrayList], *[]):
            def marker(self):
                return 'native'
        obj = C()
        obj.add('value')
        self.assertEqual(obj.get(0), 'value')
        self.assertEqual(obj.marker(), 'native')
        self.assertIsInstance(obj, ArrayList)

    def test_java_interfaces(self):
        from java.lang import Runnable
        from java.util.concurrent import Callable
        events = []
        class C(*[Runnable], *[Callable]):
            def run(self):
                events.append('run')
            def call(self):
                return 'called'
        obj = C()
        obj.run()
        self.assertEqual(obj.call(), 'called')
        self.assertEqual(events, ['run'])
        self.assertIsInstance(obj, Runnable)
        self.assertIsInstance(obj, Callable)

    def test_empty_bases_retain_legacy_class_model(self):
        class Plain:
            pass
        class Expanded(*[], *()):
            pass
        self.assertIs(type(Expanded), type(Plain))
        self.assertEqual(Expanded.__bases__, ())

    def test_class_keywords_remain_explicitly_unsupported(self):
        for header in ('metaclass=type', '*[A], metaclass=type', '**{}', '*[A], **{}'):
            with self.assertRaises(SyntaxError):
                compile('class C(%s): pass' % header, '<unsupported-class>', 'exec')

    def test_invalid_ast_contexts_and_values(self):
        for value in (None, ast.Name(id='bases', ctx=ast.Store()),
                      ast.Starred(value=ast.Name(id='bases', ctx=ast.Load()), ctx=ast.Load())):
            tree = ast.parse('class C(*bases): pass')
            tree.body[0].bases[0].value = value
            with self.assertRaises(SyntaxError):
                compile(ast.fix_missing_locations(tree), '<bad-base>', 'exec')
        for context in (ast.Store(), ast.Del()):
            tree = ast.parse('class C(*bases): pass')
            tree.body[0].bases[0].ctx = context
            with self.assertRaises(SyntaxError):
                compile(tree, '<bad-star-context>', 'exec')
        tree = ast.parse('class C(A): pass')
        tree.body[0].bases = [None]
        with self.assertRaises(SyntaxError):
            compile(tree, '<missing-base>', 'exec')

    def test_unreachable_ast_validation(self):
        tree = ast.parse('if False:\n class C(*bases): pass')
        tree.body[0].body[0].bases[0].value = None
        with self.assertRaises(SyntaxError):
            compile(tree, '<unreachable-class>', 'exec')


def test_main():
    suite = unittest.TestSuite()
    for case in (ClassBasesTests, NativeClassBasesTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError('native class bases regression failed')


if __name__ == '__main__':
    unittest.main()
