# Native yield-from validation

## Scope

This stage implements generator delegation in the native
ANTLR → AST → scope analysis → ASM/JVM bytecode pipeline. Python source is not
translated and native execution is not delegated to CPython. The optional
separate-process backend is unchanged. The project version remains
**2.7.5b2-DEV**; compiled-module API advances from **48** to **49** for the new
runtime helpers and generator-return/paused-frame behavior.

Supported behavior:

- `yield from expression` evaluates the operand and obtains its iterator once.
- Next and `send(None)` advance the delegate's next slot; non-None input calls send.
- Return values from invoked iterator methods terminate delegation through StopIteration.value, preserving arbitrary object identity, including tuples and exceptions.
- Generator `return value` is permitted, including before an unreachable yield and through a finally block that itself suspends.
- Throw forwards the original argument count, objects and traceback without constructing a new exception at every delegation level. Construction happens at the receiver when required.
- Missing throw forwards ordinary exceptions to the outer generator; failed throw attribute lookup leaves the outer generator suspended.
- GeneratorExit calls the delegate's close, not throw. Delegate close return values are ignored; failed close attribute lookup is reported as unraisable and closing continues. Failures from actually calling close propagate through the outer generator.
- A generator that catches GeneratorExit and returns a value returns it from close, as in the covered CPython 3.15.2 behavior. Repeated close returns None.
- StopIteration at the delegation cleanup boundary follows CPython 3.15's CLEANUP_THROW behavior, including external injection when no throw method exists, and StopIteration raised by calling delegate.close.
- Reentrant send, throw and close are rejected before modifying saved input. Native Python/Java identity and ThreadState conventions are retained.
- Generators expose read-only gi_yieldfrom and an __next__ alias alongside legacy next. Completed frames clear delegation and saved-local references.
- ast.YieldFrom(value) supports visitors, Python subclasses, locations, manual AST compilation and GC traversal. The indexer preserves operand references and parent links with a conservative Unknown result type.

The StopIteration value is a type-specific data descriptor backed by an internal
PyBaseException field. It is independent of args and the instance dictionary,
and is visible to GC even if args is replaced. Deleting value sets it to None.
Delegation reads the internal field, not an overridden Python subclass property.
Py.StopIterationValue constructs a single argument so a tuple result cannot be
mistaken for multiple exception arguments.

The compiler holds a YieldFromSupport instance in a typed local across each
suspension. Pending expressions, call operands and augmented-assignment targets
survive resumption. Pending generator returns also use typed locals rather than
the legacy unsaved return slot; this preserves their value through a suspending
finally and exposes the reference to frame traversal. Java tests isolate saved
locals in a separate frame so GC checks cannot pass through unrelated locals.

## Boundaries

This is not a complete Python 3.15.2 runtime or an unrestricted PEP 380 claim.
PEP 479 is not enabled: explicitly raised StopIteration escaping a generator
retains the existing legacy termination behavior. Async generators, coroutines,
await and general modern iteration semantics remain separate work.

Yield-from anywhere inside a comprehension is conservatively rejected with
`yield from inside comprehensions requires modern comprehension scopes`.
This includes first iterable clauses and nested lambdas that CPython may allow.
The boundary avoids silently adopting Python 2 comprehension scope behavior;
modern comprehension scopes are not implemented here. Existing comprehensions
without yield-from are unchanged.

The delegation path understands a type's __next__ slot, legacy next, sequence
iteration and native Java iterators. It does not add __next__ compatibility to
every legacy iterator entry point. Existing exception/throw argument conventions
remain transitional, including legacy API validation and retained multi-argument
throw support. This stage does not claim modern deprecation warnings, all error
wording, sys.unraisablehook, tracing event parity, tail-call delegation or a
constant-stack optimization for arbitrarily deep delegate chains.

Root AST operand context and required-value validation are covered; this is not
complete recursive validation of all legacy ASTs. Generated ASM code is the
supported native path, not a migration of the alternate legacy bytecode VM.
A future runtime with full PEP 479 must revisit escaped StopIteration explicitly.
See [migration status](../PYTHON3_MIGRATION.md).

## Validation

Environment: Linux, Tencent Kona OpenJDK **17.0.20-ga**, Ant **1.10.15**, Java 8
source/target. An actual Java 8 JVM, Windows and macOS were not tested. Shared
protocol tests use exactly **CPython 3.15.2** for comparison.

| Check | Result |
| --- | --- |
| Standard incremental build | Successful |
| New native Python suite | 51 passed, no skips |
| Exact CPython comparison | 45 shared cases passed, 6 JVM-only cases skipped |
| Selected standard Java | 152 passed: 62 core and 90 indexer cases |
| Independent fresh build | Successful: 922 production and 146 Java test sources compiled |
| Selected fresh Java | 152 passed |
| Fresh native Python suite | 51 passed, no skips |
| Complete Java regression | 34,899 cases passed; 61 classes: 60 passed, 1 no_cases; no failures or timeouts |
| Broad native regression | 53 modules: 52 passed, test_descr skipped (cannot import name verify) |

Overlapping runs are not summed. The six native-only tests cover Java iterable
identity, legacy next and explicit StopIteration behavior, malformed AST
operands, new-node metadata, conservative comprehension rejection and legacy
unraisable reporting. There are seven new Java runtime/AST/GC tests and two new
indexer tests. The selected Java list is deduplicated; a temporary run repeated
UnpackingTest and reported 158, which is not the final 152-case result.

Before final broad regression, all eight related modules passed: test_generators,
test_generators_jy, test_syntax, test_ast, test_ast_jy,
test_python3_named_expressions, test_python3_matmul and
test_python3_decorator_expressions. The final broad command also retains every
module from the preceding 51-module assignment-expression stage.

The existing test_descr import skip is still selected and is not counted as a
pass. The complete Java driver discovers ConstructorSignatureTest with no cases;
that is reported separately. No existing indexer reference assertions were
removed or weakened. The historical refs.foo failure from an earlier stage is
not claimed fixed based only on later successful runs.

## Findings

Exact CPython behavior was checked against local 3.15.2 sources:
`build/cpython-3.15.2/Python-3.15.2/Objects/genobject.c` and
`build/cpython-3.15.2/Python-3.15.2/Python/bytecodes.c`.

The first protocol run showed that throwing into a delegate whose throw property
raises must not terminate the outer frame. Lookup now occurs under the running
guard before resuming it. The resulting callable is held in an injection record
and used once. Raw throw forwarding also avoids repeated execution of a custom
exception constructor along a nested delegation chain.

An initial extra test assumed an externally injected StopIteration with no
throw method would reach an outer except block. The exact CPython run instead
completed delegation with its value. The CLEANUP_THROW implementation confirmed
this, so both the test and native path follow that concrete target behavior.
A companion case covers StopIteration raised by delegate.close. The initial
assumption was not accepted as a passing result or retained as a silent mismatch.

Bare incomplete `yield from` is a SyntaxError in both interpreters; an open
parenthesis remains incomplete input. Tests were corrected to distinguish these
cases rather than changing a correct interactive parser. Native unraisable
capture uses a text-compatible legacy StringIO instead of a binary stream.

Old Jython-only doctests that rejected generator return values now compile and
exercise termination values. The expected public generator attribute list adds
gi_yieldfrom. The lib-python/2.7 originals are not rewritten; the existing Lib
override carries the native migration expectations. The first related run's one
failure was the outdated attribute list and was rerun after correction.

ASDL, AST visitors/exposure, template mappings and generator GC support were
updated together. YieldFromDerived was generated with the existing template
workflow from src/templates. Only the new node was added; no bulk rewrite of
legacy AST nodes or Derived classes was performed. Normal builds use checked-in
Java sources and do not require the legacy ASDL generator.

CPython's warnings for multi-argument throw and return inside finally, along
with Java deprecation/security/logging warnings, remain visible in logs. They
are not test failures and are not hidden by suppressing output or exit codes.

## Reproduction

From the repository root with a JDK and Apache Ant:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_yield_from.py -v
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_yield_from.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.YieldFromTest org.python.core.NamedExpressionTest org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
python3 tests/cpython/run_jython_regression.py --reports build/native-yieldfrom/junit-final
```

The driver under tests/cpython uses host Python only to orchestrate native JVM
tests. It uses the standard exploded build/exposed, build/classes and
build/testclasses layout and a 120-second default per-class timeout. It is not
CPython-backend acceptance.

The broad native command selects 53 modules:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_yield_from test_python3_named_expressions test_python3_matmul test_operator test_tokenize test_augassign test_python3_decorator_expressions test_python3_class_bases test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_generators_jy test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration test_class test_class_jy test_classdecorators test_descr test_descr_jy test_metaclass test_java_subclasses test_subclasses_jy test_gc_jy
```

The final fresh build uses independent intermediates and distribution directories:

```sh
ant -Dbuild.dir=build/native-yieldfrom/verified -Ddist.dir=build/native-yieldfrom/verified-dist jar copy-dev compile-test jar-test
java -Dpython.home=build/native-yieldfrom/verified-dist -cp 'build/native-yieldfrom/verified/testclasses:build/native-yieldfrom/verified-dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.YieldFromTest org.python.core.NamedExpressionTest org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
java -Dpython.home=build/native-yieldfrom/verified-dist -cp 'build/native-yieldfrom/verified/testclasses:build/native-yieldfrom/verified-dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_yield_from.py -v
```

Local ignored Ant jars were invoked as
`java -cp 'build/tools/*' org.apache.tools.ant.Main` instead of installed ant.
The exact CPython executable is required only for comparison. Classpath
separators shown are for Linux/macOS; use semicolons on Windows. Run copy-dev
after library/test edits; Lib alone is not a complete standard library. jar-test
creates dependencies used by Java interoperability subprocess tests.

Final logs under ignored build/native-yieldfrom are build-final.log,
python-final.log, cpython-final.log, java-final.log, fresh-build.log,
fresh-java.log, fresh-python.log, full-java.log, junit-final/summary.json and
per-class logs, regression-final.log and related-final.log. Intermediate
build.log, python.log, cpython.log and related.log are diagnostic attempts, not
final acceptance. Final fresh artifacts are under verified/verified-dist; earlier
fresh and final-fresh directories belong to intermediate versions. No build/dist
artifacts are part of the source change.
