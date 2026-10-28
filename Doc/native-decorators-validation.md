# Native expression-decorator validation

## Scope

This stage follows [iterable class bases](native-class-bases-validation.md).
Function and class decorators accept one expression from the current native
language, following PEP 614's relaxation of the old dotted-name/optional-call
restriction:

```python
def keep(value):
    return value

registry = [keep]
@registry[0]
def answer():
    return 42

@keep if True else missing
class Example(object):
    pass
```

The ANTLR grammars parse the expression into the existing `decorator_list`.
Scope analysis checks it in the enclosing scope; the existing ASM compiler and
`PyObject.__call__` path evaluate and apply it on the JVM. No source translation,
CPython forwarding or new runtime helper is involved. The native language
version remains **2.7.5b2-DEV** and compiled-module API remains **46**. No native
AST layout or runtime calling convention changes in this stage.

The supported expression language still excludes assignment expressions,
matrix multiplication, `async`/`await` and `yield from`. Thus this is not complete
PEP 614 coverage of every modern expression, nor complete Python 3.15.2 support.
Existing comprehension scope, eager annotation and object-model behavior is
not upgraded merely by using it in a decorator.

## Results

Platform: Linux, Tencent Kona OpenJDK 17.0.20-ga, Ant 1.10.15, using the project's
Java 8 source/target settings. Actual Java 8, Windows and macOS execution was
not verified. The shared comparison used exactly CPython 3.15.2.

| Check | Result |
| --- | --- |
| Standard build | Successful |
| Fresh build in `build/native-decorators/fresh` | Successful; 912 production and 143 Java test sources compiled |
| New native Python module | 39 cases passed, no skips |
| CPython 3.15.2 comparison | 33 shared cases passed; 6 JVM-specific cases skipped |
| Selected Java classes | 42 cases passed on standard and fresh tests with the distribution JAR, including 5 new decorator cases |
| Fresh JAR-based Java run including the indexer | 125 cases passed: 42 selected cases plus 83 indexer cases |
| Complete Java driver using standard exploded classes | 58 classes; 56 passed, 1 failed, 1 with no cases; 34,872 cases, 1 failure, no timeouts |
| Broad native Python regression | 46 modules selected: 45 passed, 1 existing `test_descr` skip, no failures |

Counts from overlapping runs must not be added together. The complete Java
driver uses host Python only to launch independent JVM processes. Its directory
name `tests/cpython` does not make it a CPython backend test. Native tests use
`PythonInterpreter` or `org.python.util.jython` without selecting CPython.

The final broad Python regression exited **0**; the complete Java driver exited
**1** because of the retained indexer failure detailed below. Neither the Python
success nor the JAR-based Java success overrides that failure.

The broad Python regression includes all nine migration modules plus the class,
decorator, AST, scope, generator, Java integration and GC modules from the prior
stage. `test_descr` is selected but already has an existing skip expectation
because its override imports removed `test_support.verify`/`vereq` helpers.
The test and skip list are unchanged; unexecuted coverage is not counted as a
passing module. Security Manager and logging-permission warnings are not hidden.

## Coverage and implementation

The shared module checks subscripts, slices, tuple expressions, parenthesized
and bare lambdas, conditional and boolean short-circuiting, chained calls and
attributes, list/set/dict/generator comprehensions, expanded displays and calls,
multiline decorators, comments and explicit line continuation. A custom operator
and registry check callback behavior and single lookup. It also exercises 80
stacked decorators, non-callable results, syntax boundaries and AST round trips
with source positions.

Function and class tests assert top-to-bottom expression evaluation before
function defaults or class bases/body, bottom-to-top application, replacement
objects, failure timing and preservation of the previous binding. Closures,
class-local descriptors, prior bindings and `nonlocal` definitions are covered.
Generator tests suspend inside consecutive decorators, function defaults and
expanded class bases, and check `throw()` and `close()` cleanup.

Six native-only cases cover Java collection lookup, decorated Java inheritance,
invalid root AST contexts, missing decorators and misplaced stars, unreachable
AST validation and explicit rejection of unmigrated expression forms. Scope
checks are not claimed to recursively validate every legacy AST shape.

Five Java tests verify actual native `PyFunction`/`PyType` identity, a Java method
used as decorator, the `ThreadState` calling convention, Java replacement-object
identity, invocation of a decorated Java interface proxy from Java, existing AST
node types and a partially evaluated decorator array in a suspended frame. The
last case verifies GC traversal and identity-based direct references before
resuming the function definition. No new frame/GC code was needed; this uses
the array traversal added in the preceding class-base stage.

The full and partial grammars now use `AT test NEWLINE`, preserving the `@after`
AST return convention. A tuple needs parentheses; a bare starred decorator is
invalid. Old simple/dotted forms retain their behavior. The old
`test_decorators.test_errors` check now compiles the newly allowed expressions
and asserts their non-callable runtime errors under Jython instead of expecting
syntax errors. The non-Jython Python 2 branch keeps its original expectation;
no test was removed or skipped to accommodate the feature.

Indexer class conversion previously discarded decorators. `NClassDef` now
retains them, resolves their references in the outer scope and includes them
in visitor traversal. `NFunctionDef` already resolved its decorator list but
now also exposes that list to visitors. Three new indexer cases check expression
references, source offsets, enclosing-scope resolution, parent links, visitors
and serialization round trips. Existing Java constructors remain available.
The class index node's serialization UID changes to `2` to reject old disk ASTs
that lack the decorator list; `AstCache` already falls back to source parsing
after deserialization errors. This cache version is separate from runtime API 46.

Indexer tests cover subscripts and conditional decorators. They do not establish
complete alternate-AST support for all modern expressions, decorator result-type
inference, or accurate decorated class/function replacement modeling.

## Reproduction

From the repository root, with a JDK and Ant installed:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_decorator_expressions.py -v
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_decorator_expressions.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest
python3 tests/cpython/run_jython_regression.py --reports build/native-decorators/junit-final
```

The exact CPython executable is needed only for the comparison. The Java driver
requires host Python 3.9+. The test classpath uses Linux/macOS separators; use
`;` on Windows. `jar-test` supplies `dist/jython-test.jar` used by Java integration
subprocesses. `copy-dev` assembles `dist/Lib` from the Python 2.7 library and
Jython overrides; rerun it after editing library tests.

The full fresh build and 125-case run used:

```sh
java -Dbuild.dir=build/native-decorators/fresh -cp 'build/tools/*' org.apache.tools.ant.Main jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/native-decorators/fresh/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
```

Project-local Ant JARs in ignored `build/tools` are not committed and are not
needed when Ant is installed; `ant -Dbuild.dir=build/native-decorators/fresh`
can replace that Java command prefix. Standard and fresh builds both update
`dist`, so they were run sequentially. The complete Java driver retained the
standard exploded layout because legacy fixtures depend on it.

The broad native regression command is:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_decorator_expressions test_python3_class_bases test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration test_class test_class_jy test_classdecorators test_descr test_descr_jy test_metaclass test_java_subclasses test_subclasses_jy test_gc_jy
```

## Remaining failure

The complete Java driver still reports the previously recorded failure:

```text
org.python.indexer.IndexerTest.testBasicDefsAndRefs
No reference to refs.foo at offset 266 of length 3
```

Its 83-case `IndexerTest` run passed the three new tests and all other cases.
The failure assertion and fixture are unchanged. `ConstructorSignatureTest` has
no discovered cases. The other 56 classes passed; the complete driver exits
nonzero and is **not all green**.

A JAR-based indexer run passed all 83 cases, also as part of the fresh 125-case
run. That observation does not override the complete driver's failure or prove
the defect fixed. The runs use different classpaths/configurations. This stage
has not established the root cause of that discrepancy or completed a clean
historical-checkout comparison. In particular, `refs.py` contains no class
decorator: class decorator retention must not be credited as its fix.

Raw logs are in ignored `build/native-decorators/`: `build-final.log`,
`fresh-build.log`, `python-final.log`, `cpython-final.log`, `java-final.log`,
`fresh-java.log`, `full-java.log`, `junit-final/summary.json`, per-class logs and
`regression-final.log`. Earlier `build.log`, `python.log`, `cpython.log`,
`test-build.log`, `java.log` and `indexer.log` are intermediate checks; the last
of those predates the third added indexer case. Final counts above refer to the
final logs, not intermediate or duplicated invocations.

Full modern class creation, language/object-model migration, standard-library
upgrading and remaining syntax are still outstanding. See
[migration status](../PYTHON3_MIGRATION.md) for the overall boundaries.
