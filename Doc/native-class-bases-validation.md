# Native iterable class-base validation

## Scope

This stage follows [generalized calls](native-call-validation.md) and implements
iterable expansion in native class definitions:

```python
class Left(object):
    pass
class Right(object):
    pass
class Combined(*[Left], *[], Right):
    pass
assert Combined.__bases__ == (Left, Right)
```

The ANTLR parser, Java AST, scope analysis and ASM compiler execute this on the
JVM. There is no Python 2 source rewrite and no CPython forwarding. Expansion
reuses `UnpackingSupport.extendList` and the existing `Py.makeClass` factory.
It preserves Java inheritance and interface proxies without claiming the full
Python 3 class-creation protocol. The language version remains **2.7.5b2-DEV**;
the native Python 3.15.2 runtime and standard library are not complete.

Compiled-module API **46** invalidates caches made with the older class-base
parser and class-decorator evaluation order. It is a bytecode/cache compatibility
number, not a Python version. This stage adds no new production helper class.

## Acceptance

Environment: Linux, Java 17, Ant 1.10.15, using the project's Java 8 source/target
settings. An actual Java 8 JVM, Windows and macOS were not tested in this stage.

| Check | Result |
| --- | --- |
| Standard build | Successful |
| Fresh build in `build/native-class-bases/fresh` | Successful; 912 production and 142 Java test source files compiled |
| New native Python module | 44 cases passed, no skips |
| Shared module on CPython 3.15.2 | 37 shared cases passed; 7 JVM-specific cases skipped |
| Selected native Java tests | 37 cases passed on standard and fresh builds, including 7 new class-base cases |
| Broad native Python regression | 45 modules selected: 44 passed, 1 existing `test_descr` skip, no failures |
| Complete non-interactive Java driver | 57 discovered classes; 55 passed, 1 failed, 1 with no cases; 34,864 cases, 1 failure, no timeouts |
| Final diff check | `git diff --check` passed; new-file whitespace and final newlines checked |

Native acceptance uses `org.python.util.jython` without the CPython runtime
property, or `PythonInterpreter` directly. Only the shared comparison uses
CPython. The host Python process used by the Java driver merely orchestrates
JVM tests. Selected Java cases are already included in the complete-driver
count and must not be added to it. A class with no cases is not a passing case.

The new Python module checks single/multiple/empty expansions, mixed ordinary
bases, conditional and lambda operands, nested displays and calls, sequences,
iterators and generators, immediate consumption, exception propagation, source
immutability, duplicate bases, MRO conflicts, parenthesized tuple expressions,
closures, class scopes, `nonlocal`, inherited metaclasses, AST round trips,
interactive input and 80 empty expansions. Decorator cases verify evaluation
before bases/body, reverse application, failures and class replacement.
Generator cases suspend in decorators, normal/starred bases and nested displays,
and exercise `throw()` and `close()`.

Native-only cases cover Java iterable bases, Java class inheritance, multiple
Java interfaces, legacy empty-base behavior, rejected class keywords and invalid
or unreachable ASTs. Java tests check native object identity, actual interface
invocation from Java, the four-field AST, saved arrays and suspended-frame GC
edges. One new indexer case checks references to every star operand and the
classes used to build its input lists.

## Reproduction

From the repository root, with a JDK and Ant installed:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_class_bases.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest
python3 tests/cpython/run_jython_regression.py --reports build/native-class-bases/junit-default
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_class_bases.py -v
```

The comparison requires the optional exact CPython 3.15.2 installation, not
needed by the native runtime. The Java driver requires host Python 3.9+.
Classpath separators above are for Linux/macOS; Windows uses `;`.

The fresh build and selected fresh Java tests used:

```sh
java -Dbuild.dir=build/native-class-bases/fresh -cp 'build/tools/*' org.apache.tools.ant.Main jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/native-class-bases/fresh/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest
```

Project-local Ant jars in ignored `build/tools` are not committed or required
when Ant is installed. The equivalent standard command begins with
`ant -Dbuild.dir=build/native-class-bases/fresh`. Fresh builds also update
`dist/jython-dev.jar`; do not build concurrently into that shared distribution.
The complete Java driver used the standard `build/classes`, `build/exposed` and
`build/testclasses`, because legacy fixtures depend on that layout.
`jar-test` supplies `dist/jython-test.jar` for Java integration subprocesses.

The expanded 45-module regression command is:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_class_bases test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration test_class test_class_jy test_classdecorators test_descr test_descr_jy test_metaclass test_java_subclasses test_subclasses_jy test_gc_jy
```

After editing tests under `Lib`, run `ant copy-dev` before this command. The
assembled `dist/Lib` combines the upstream `lib-python/2.7` library with Jython
`Lib` overrides. An intermediate attempt to prepend `-Dpython.path=Lib` failed
before tests with an `encodings.aliases` import error; `Lib` is not a standalone
complete standard library. Final validation uses the assembled standard layout,
with the updated boundary assertion confirmed in its imported test module.

## Issues found and fixed

The first grammar implementation assigned the `class_base` rule's tree inside
its alternatives. ANTLR's later `rulePostProcessing` replaced that tree, dropping
starred bases. The first 44-case native run had 32 failures and 4 errors; all six
then-existing Java class-base cases failed. The rule now stores the expression
in a local and publishes it in `@after`. All 44 Python cases then passed.

A remaining Java GC failure exposed missing strong edges: suspended compiler
locals included a `PyObject[]` containing evaluated decorators, but frame
traversal ignored its elements. `PyFrame.traverse` and `refersDirectlyTo` now
handle those arrays, skip null slots, use identity checks and propagate visitor
early returns. A separate array case and the generator case both pass among the
final seven Java class-base tests. This also covers saved base and argument
arrays, without introducing arbitrary recursive `Object[]` traversal.

The old compiler evaluated class-decorator expressions after executing the
class body. It now evaluates them top-to-bottom before bases/body, saves them
in typed locals, then applies them bottom-to-top after class construction.
This correction applies to both starred and ordinary bases. Base expressions
remain in the surrounding scope; the class body enters its own scope.

The old parser flattened any tuple expression into separate bases, incorrectly
accepting `class C((A, B))` as two bases. Explicit list parsing preserves that
as a single tuple expression, rejected by the runtime, while `class C(*(A, B))`
expands it. Existing class AST fields and constructors are unchanged. The class
factory copies the input base array into its tuple; compiler cleanup therefore
does not clear the source tuple or saved class/metaclass bases.

The first 45-module run found one obsolete expectation in
`test_python3_unpacking`: it still required `class C(*bases)` to be a syntax
error. The boundary case now actually creates and instantiates the subclass,
checks `__bases__`, and retains rejection checks for unsupported comprehensions,
invalid starred dictionary entries and class-header `**mapping`. The module
still has 42 cases; the check was not removed or skipped.

After synchronizing the updated library test, the final standard-layout rerun
reported **44 tests OK** and **1 test skipped**, with no failures. The passing
modules include all eight migration modules and the selected class, decorator,
Java subclass and GC regression modules. This is not an all-45-modules pass.

`test_descr` could not import the old `test.test_support.verify` helper.
Its legacy override also imports `vereq`; this mismatch is already listed in
`Lib/test/regrtest.py`'s existing Jython skip expectations. Neither that test nor
the skip list was changed. This is an unexecuted module, not passed descriptor
coverage. `test_descr_jy` is selected independently. Existing Java Security
Manager and logging-permission warnings remain visible rather than suppressed.

## Complete Java results

The driver reported 57 classes: 55 passed, 1 failed and 1 had no cases. There
were 34,864 reported cases, one failure and no timeouts.
`ConstructorSignatureTest` has no discovered cases. `ClassBasesTest` passed
all seven cases. `IndexerTest` ran 80 cases, including the new class-base
reference check, with only this failure:

```text
org.python.indexer.IndexerTest.testBasicDefsAndRefs
No reference to refs.foo at offset 266 of length 3
```

This failure was also recorded in earlier migration stages and remains
unresolved. No clean historical-checkout comparison has conclusively attributed
its cause. The complete driver exits nonzero; this is not an all-green run.
The new class-base reference test and existing standard-library indexer case
passed. Indexer conversion preserves star-operand references but does not infer
all iterable elements, dynamic inheritance or MROs.

## Logs and boundaries

Raw logs remain under ignored `build/native-class-bases/`:

- `build-final.log`, `python-final.log` and `java-final.log` record the successful standard build and targeted native tests.
- `fresh-build.log` and `fresh-java.log` record the fresh build and 37 selected Java passes.
- `cpython-comparison.log` and `cpython-final.log` record 37 shared passes and 7 JVM-only skips on CPython 3.15.2.
- `full-java.log` and `junit-default/summary.json` record the complete Java run; per-class logs include the remaining failure.
- `regression.log` preserves the first broad run and obsolete assertion failure. `final-regression.log` is the failed library-path experiment, not an acceptance result. `copy-dev-final.log`, `library-check.log` and `regression-final.log` record the standard-layout rerun.
- `python-tests.log` and `java-tests.log` preserve the initial parser failures. `python-fixed.log` records 44 Python passes after the grammar fix; `java-fixed.log` retains the subsequent GC failure before its repair.

`metaclass=`, other class-header keywords and class-header `**mapping` remain
unsupported. There is no new `__build_class__`, `__prepare__`,
`__mro_entries__`/`__orig_bases__`, `__classcell__`, zero-argument `super` or
complete modern class-hook protocol. Existing inherited metaclasses still use
the legacy factory. No-base classes, including empty expansions, retain the
legacy class model rather than implicitly becoming Python 3 `object` subclasses.

The AST remains four-field `ClassDef(name, bases, body, decorator_list)`, not
CPython's modern class AST. Python iterators still need native `next`; exact
length-hint callbacks, error text and the complete modern object model are not
promised. No standard-library version upgrade is claimed by these results.
See [migration status](../PYTHON3_MIGRATION.md) for the remaining work.
