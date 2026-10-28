# Native generalized-call validation

## Scope

This stage follows [mapping displays](native-mapping-validation.md) and adds
multiple `*iterable` and `**mapping` operands to native function calls:

```python
def collect(*args, **kwargs):
    return args, kwargs

assert collect(0, *[1], 2, *[3], x=4, **{'y': 5}, z=6, **{'w': 7}) == (
    (0, 1, 2, 3), {'x': 4, 'y': 5, 'z': 6, 'w': 7})
```

Execution uses the native ANTLR parser, Java AST, scope analysis, ASM compiler,
and JVM runtime. It does not rewrite source to Python 2 or call CPython.
`CallUnpackingSupport` accumulates values and invokes the existing
`PyObject.__call__(ThreadState, PyObject[], String[])` ABI. Typed locals and
`Traverseproc` support preserve intermediate state across generator suspension.
Compiled-module API **45** prevents older runtimes from loading modules that
require this helper. The advertised language version remains **2.7.5b2-DEV**;
the complete native Python 3.15.2 runtime and standard library are not finished.

## Acceptance

Environment: Linux, Java 17, Ant 1.10.15, with the project's Java 8 source/target
settings. An actual Java 8 JVM, Windows and macOS were not tested in this stage.

| Check | Result |
| --- | --- |
| Standard build | Successful, including the indexer fix |
| Fresh build in `build/native-call/fresh-final` | Successful; 912 production and 141 Java test source files compiled |
| New native Python module | 49 cases passed, no skips |
| Shared module on CPython 3.15.2 | 42 shared cases passed; 7 JVM-specific cases skipped |
| Selected native Java tests | 30 cases passed on both standard and fresh builds, including 6 new call cases |
| Broad native Python regression | All 35 modules OK; includes 247 cases across the seven migration modules |
| Complete non-interactive Java driver | 56 discovered classes; 54 passed, 1 failed, 1 with no cases; 34,856 cases, 1 failure, no timeouts |
| Final diff check | `git diff --check` passed |

Native acceptance uses `org.python.util.jython` without the CPython runtime
property, or `PythonInterpreter` directly. Only the explicitly identified shared
comparison uses CPython. Selected Java tests also occur in the complete-driver
totals and must not be added to them as distinct cases. The driver follows the
existing non-interactive discovery/exclusion rules, not every platform or
interactive test. A class with no discovered cases is not a passing test case.

Coverage includes empty and interleaved calls, conditional/lambda operands,
positionals after stars, stars written after explicit keywords, modern function
signatures, binding conflicts, duplicate keys, Unicode and non-identifier string
keys, delayed string-key validation, generic mapping protocols, live key lists,
key-iterator exhaustion, dictionary subclass dispatch, exception propagation,
source immutability, object identity, shadowed builtins, closures, comprehensions,
decorators, AST round trips and partial interactive input. Generator tests suspend
in the callable, normal and starred arguments, consecutive named values, mapping
operands and nested calls; they also exercise `throw()` and `close()`.

Native-only cases cover Java iterables, arrays, maps, overloaded methods and
constructors, native namespaces, legacy AST fields, rejected mixed AST layouts,
invalid expression contexts and unreachable duplicate names. Java tests also
check the existing call ABI and GC traversal through `PyFrame.f_savedlocals`.
Two new indexer cases verify references in single and multiple star/mapping calls.
The larger shared case contains 80 stars and 80 mapping operands in one call.

## Reproduction

From the repository root, with a JDK and Ant installed:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_call_unpacking.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest
python3 tests/cpython/run_jython_regression.py --reports build/native-call/junit-final
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_call_unpacking.py -v
```

The CPython comparison requires the optional exact 3.15.2 installation; native
execution does not. The Java driver uses host Python 3.9+ only for orchestration,
despite its location under `tests/cpython`. The classpath separator above is for
Linux/macOS; Windows uses `;`.

The final fresh build, including the indexer fix, used:

```sh
java -Dbuild.dir=build/native-call/fresh-final -cp 'build/tools/*' org.apache.tools.ant.Main jar copy-dev compile-test jar-test
```

Project-local Ant jars under ignored `build/tools` are not committed; an ordinary
`ant -Dbuild.dir=build/native-call/fresh-final ...` invocation is equivalent. Selected
fresh Java tests used `build/native-call/fresh-final/testclasses` and the freshly
produced `dist/jython-dev.jar`. The broad Python regression also used that JAR.
The complete Java driver used the standard `build/classes`, `build/exposed`, and
`build/testclasses` from the successful standard build of the same sources.
Several legacy Java fixtures depend on that standard directory layout.
`jar-test` supplies `dist/jython-test.jar` for Java integration subprocesses.

The 35-module regression command was:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration
```

Raw logs are retained in ignored `build/native-call/`. `indexer-build.log` and
`fresh-final-build.log` record final standard and fresh builds. The earlier
`build-final.log` and `fresh-build.log` predate the indexer fix.
`targeted-regression.log` records 49 call cases plus AST, grammar and extended-call
regression. `java-tests.log` and `fresh-final-java-tests.log` record the final six
selected classes, 30 cases each; `indexer-tests.log` records the 79-case rerun.
`cpython-comparison.log` records 42 shared passes and 7 skips.
`regression.log` retains the first broad run; `final-regression.log` records all
35 modules passing after the indexer fix. `full-java.log` and
`junit-default/summary.json` retain the first complete Java run with two failures;
`full-java-final.log` and `junit-final/summary.json` record the final run with one
failure. Earlier `python-tests.log` contains the intermediate 47-case run, not
the final 49-case result.

## Issues found and semantic details

An empty Java hash table may skip hashing in `containsKey`. The first new
negative case exposed item lookup occurring before rejection of an unhashable
first mapping key. The helper now validates that key's hash before item lookup.
Repeated keys are also detected before asking the mapping for another value.
Calling expansion never reuses dictionary-display overwrite behavior.

Using `Py.iter` with a custom argument-error message would mask a `TypeError`
raised inside a user's `__iter__`. The new helper instead calls the native
iteration protocol directly. Dedicated cases check exception text is preserved
for both single-star and multiple-star calls. The Java GC test initially used
an unavailable no-argument `PyFrame` constructor; it was corrected to the real
constructor and passed with the remaining Java cases.

The first 35-module regression passed 33 modules and exposed two old expectation
conflicts. `test_grammar` still expected a positional value after a star to be a
syntax error, and its `eval` did not provide the local function name. The native
branch now checks the successful result with an explicit namespace; non-Jython
Python 2 retains the old expectation. `test_extcall` had eight exact error-text
expectations from the old helper. All 66 doctest examples remain, with updated
exact native iteration/mapping messages rather than removed or skipped checks.
The AST fixture was updated to assert modern expansion entries and their source
positions. Explicit `None`, `True`, `False` and `__debug__` keyword names are
rejected; the same strings remain valid when supplied through a mapping.

Final targeted and full 35-module reruns passed. Existing Java Security Manager
deprecation and logging-permission warnings remained visible during Java
integration; they did not fail that regression.

The first complete Java run reported 34,854 cases with two failures in
`IndexerTest`: the previously recorded reference failure, plus a new
`testInstanceAttrsWithStdLib` failure. The indexer assumed call arguments could
be converted without handling `Starred`, causing a `ClassCastException` while
indexing `random`. `AstConverter.visitCall` now converts every star operand to
an expression for the existing reference-resolution/visitor path; null-name
mapping keywords already resolve their values. The original standard-library
case and both new single/multiple-expansion reference cases passed in the
79-case indexer rerun, which retained only the prior reference failure.
This fix does not claim complete expansion-arity or argument-binding inference,
or full Python 3 support throughout the alternate indexer AST.

CPython 3.15.2 comparisons also establish less obvious evaluation behavior:
all positional expressions precede keyword expressions even when a star is
written after a named argument. A sole starred positional operand is evaluated
before keywords but consumed after keyword merging. Other positional layouts
consume each star immediately. Consecutive named values are evaluated together
before collision checks against earlier mappings. Non-string keys are rejected
after all merges, and after consumption of a deferred sole star.

## Complete Java results

The final standard-layout driver reported 56 discovered classes: 54 passed,
1 failed and 1 had no cases. Its 34,856 reported cases contain one failure and
no timeouts. `ConstructorSignatureTest` has no discovered cases.
The sole remaining failure is:

```text
org.python.indexer.IndexerTest.testBasicDefsAndRefs
No reference to refs.foo at offset 266 of length 3
```

That class ran 79 cases, including the two new reference checks. The standard
library indexing regression introduced by modern call entries is fixed; the
reference failure above was previously recorded and remains unresolved. No
clean historical-checkout comparison has conclusively attributed its cause.
The complete driver exits nonzero for this failure; it is not an all-green run.

## Compatibility boundaries

The parser uses `Starred(value, Load)` in `Call.args` and
`keyword(arg=None, value=mapping)` in `Call.keywords`. The existing five-field
`Call` layout and Java constructors remain available. Pure old-field ASTs retain
the legacy compiler/runtime path; mixing old expansion fields and modern entries
is rejected rather than silently ignoring either. ASDL now marks the keyword
identifier optional; the existing generator and Java getter already support
null identifiers, so the Java node layout is unchanged.

The accumulator's `LinkedHashMap` does not make the final Python `**kwargs`
dictionary insertion-ordered. PEP 468, the modern dictionary object model,
`str`/`bytes` separation and modern `__next__` iteration remain outstanding.
Python iterators still need the native `next` protocol. Exact CPython length-hint
callbacks, hash/equality counts, hash reuse, concurrent mutation behavior and
error wording are not guaranteed. The AST and introspection APIs remain
transitional rather than fully CPython 3-compatible.

Starred class bases, unpacking comprehensions, the remaining language and object
model, and the modern standard library are still migration work. See
[the migration status](../PYTHON3_MIGRATION.md). Neither these targeted cases nor
the existing Java regression constitute a complete CPython 3.15.2 conformance run.
