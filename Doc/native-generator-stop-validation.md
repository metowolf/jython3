# Native generator StopIteration validation

## Scope

This stage implements PEP 479 on the existing native JVM generator execution
path. Source remains ANTLR → AST → scope analysis → ASM/JVM bytecode. CPython is
used only for comparison, never as a replacement execution backend. The optional
separate-process backend is unchanged. The project version remains
**2.7.5b2-DEV**, and compiled-module API remains **49**: the runtime exception
boundary changes, but no generated-call signature, AST shape or frame layout is
introduced here. Existing native generator code executes through this boundary;
rebuild the runtime and run copy-dev to assemble the updated library.

A StopIteration or subclass escaping an executing generator now raises
`RuntimeError("generator raised StopIteration")`. The original normalized
instance is both cause and context; suppression is true and the original
traceback, value, subclass identity and any existing cause are preserved. The
runtime does not call its constructor again or stringify it. Handlers and
finally blocks inside the generator run before conversion. An inner generator's
RuntimeError is not rewrapped by outer delegates. Saved locals, active delegate
and input are cleared on failure, and Java raw iteration receives an error
rather than silently reporting end-of-iteration.

The following are deliberately not converted:

- StopIteration caught within the generator, including one suppressed by return in finally.
- Normal return values, including tuples and StopIteration instances returned as data.
- Ordinary iterator exhaustion, including StopIteration consumed by yield-from.
- Exceptions raised by ordinary non-generator functions until they escape a generator body.
- Throwing StopIteration into an unstarted or already closed generator.
- Non-StopIteration exceptions, including GeneratorExit and already-wrapped RuntimeError.

Next/default-next, send, throw and close are covered. Generator-expression bodies
use the same runtime rule; eager evaluation of their outermost iterable remains
outside that generator body. Close cleanup raising StopIteration becomes an
error; a caught GeneratorExit followed by return still returns its value.
The preceding stage's exact CPython 3.15 CLEANUP_THROW behavior is retained:
injection into a delegate with no throw, or StopIteration from an iterator's
close method, may finish delegation rather than escape a generator.

`from __future__ import generator_stop` is accepted as a no-op, with existing
future-placement checks. The historical `0x800000` explicit compile flag is
accepted and retained by code objects and nested/dynamic compilation. Its
absence cannot disable PEP 479. As in CPython 3.15.2, the import itself does not
set the bit; `dont_inherit=True` still excludes inherited flags. The __future__
feature metadata records the original optional 3.5 beta and mandatory 3.7 alpha
releases, not this project's language version.

## Library compatibility and boundaries

The retained 2.7 contextlib now recognizes when PEP 479 wrapped the same
StopIteration injected from a with body and restores the original exception and
traceback. It does not suppress or unwrap an unrelated cleanup failure. Runtime
errors from a with body retain identity. The nested generators in difflib._mdiff
now use explicit return or exhaustion handling; otherwise HTML/context diffs
would fail once their internal streams end. Both existing library suites and
new shared setup/cleanup, empty-stream, context-window and HTML cases cover
these adjustments. The legacy generator doctest and one native yield-from case
were updated to assert conversion, not deleted or skipped.

This is not a complete Python 3.15.2 language or standard-library port. Python 2
syntax, iterator APIs and unrelated library behavior remain transitional.
Modern comprehension scopes, yield-from/walrus inside comprehensions,
async/await, asynchronous generators, coroutine-specific exception conversion,
full tracing-event parity, modern traceback APIs and the alternate PyBytecode
interpreter are not acceptance claims. Tracing may expose legacy JVM events.
Third-party generators that intentionally raise StopIteration must use return
or catch exhaustion locally; there is no per-module legacy opt-out.

## Validation

Environment: Linux, Tencent Kona OpenJDK **17.0.20-ga**, Ant **1.10.15**, with
Java 8 source/target. No actual Java 8 JVM, Windows or macOS run was performed.
Shared tests use exactly **CPython 3.15.2**.

| Check | Result |
| --- | --- |
| Standard incremental build | Successful |
| New native Python suite | 45 passed, no skips |
| Exact CPython comparison | 43 shared cases passed, 2 JVM-only cases skipped |
| Selected standard Java | 158 passed: 68 core and 90 indexer cases |
| Independent fresh build | Successful: 922 production and 147 Java test sources compiled |
| Selected fresh Java | 158 passed |
| Fresh native Python suite | 45 passed, no skips |
| Complete Java driver | 34,905 cases passed; 62 classes: 61 passed, 1 no_cases; no failures or timeouts |
| Broad native regression | 61 modules: 60 passed, test_descr skipped (cannot import name verify); exit status 0 |

The two JVM-only Python cases cover Java value identity and the legacy next
entry point. Six new Java tests cover raw iteration failure, Java callback and
ThreadState identity, cause/context/traceback GC edges, saved-frame cleanup,
native iterator completion and compiler-flag metadata. These overlap the Python
and full-Java runs and are not summed. The 158-case Java list is deduplicated;
its increase from the preceding stage's 152 is six new tests, not the duplicate
UnpackingTest invocation recorded as an intermediate attempt in that report.

An initial 11-module focused regression passed: generator-stop, yield-from,
generators, generators_jy, genexps, contextlib, difflib, __future__, future, iter
and itertools. The broader final command retains every preceding-stage module.
The existing test_descr import skip is not counted as passing. The complete
Java driver reports ConstructorSignatureTest's no_cases separately. Existing
indexer assertions were not weakened; later passing runs do not establish the
cause of an older refs.foo failure.

## Findings

Exact target behavior was checked against local CPython sources in
`build/cpython-3.15.2/Python-3.15.2/Python/intrinsics.c` and executable probes.
In particular, an unstarted generator receiving throw(StopIteration) does not
execute its body and does not take the PEP 479 conversion path. The original
exception's traceback contains its generator/helper origin; the wrapper is
created after the native frame unwinds. Tracing-event equivalence is not claimed.

The first Java metadata test assumed that a generator_stop future import sets
the historical flag. Exact CPython disproved that assumption: an import is a
no-op, while an explicit compile flag survives in module and nested code objects.
The implementation and tests now distinguish both, including dynamic compile
inheritance and dont_inherit. A missing flag in the compiler's output whitelist
was corrected without rewriting other legacy flags or changing the cache API.

## Reproduction

From the repository root with a JDK and Apache Ant:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_generator_stop.py -v
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_generator_stop.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.GeneratorStopTest org.python.core.YieldFromTest org.python.core.NamedExpressionTest org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
python3 tests/cpython/run_jython_regression.py --reports build/native-generator-stop/junit-final
```

The Python driver orchestrates native JVM Java tests using build/exposed,
build/classes, build/testclasses and extlibs. It is not CPython-backend
acceptance; its default per-class timeout is 120 seconds.

The broad native run selects 61 modules:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_generator_stop test_python3_yield_from test_python3_named_expressions test_python3_matmul test_operator test_tokenize test_augassign test_python3_decorator_expressions test_python3_class_bases test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_generators_jy test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration test_class test_class_jy test_classdecorators test_descr test_descr_jy test_metaclass test_java_subclasses test_subclasses_jy test_gc_jy test_genexps test_contextlib test_difflib test___future__ test_future test_iter test_itertools
```

The independent fresh build and tests use their own intermediates and dist:

```sh
ant -Dbuild.dir=build/native-generator-stop/fresh -Ddist.dir=build/native-generator-stop/fresh-dist jar copy-dev compile-test jar-test
java -Dpython.home=build/native-generator-stop/fresh-dist -cp 'build/native-generator-stop/fresh/testclasses:build/native-generator-stop/fresh-dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.GeneratorStopTest org.python.core.YieldFromTest org.python.core.NamedExpressionTest org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
java -Dpython.home=build/native-generator-stop/fresh-dist -cp 'build/native-generator-stop/fresh/testclasses:build/native-generator-stop/fresh-dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_generator_stop.py -v
```

In this workspace, ignored local Ant jars were invoked as
`java -cp 'build/tools/*' org.apache.tools.ant.Main` instead of installed ant.
The exact CPython executable is needed only for comparison. Lib alone is not a
complete standard library: copy-dev combines it with lib-python/2.7. jar-test
builds dependencies for Java interoperability subprocesses. Classpath separators
shown are for Linux/macOS; Windows requires semicolons.

Final logs under ignored build/native-generator-stop: build-final.log,
python-final.log, cpython-final.log, java-final.log, fresh-build.log,
fresh-java.log, fresh-python.log, full-java.log, junit-final/summary.json and
per-class logs, and regression-final.log. Earlier build.log, python.log,
java-initial.log and related.log are intermediate evidence, not substituted for
final results. Build products and helper scripts are not source deliverables.
