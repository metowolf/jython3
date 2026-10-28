# Native JVM migration validation

This report records the iterable-unpacking stage at compiled-module API 43.
For the subsequent dictionary-mapping stage and API 44 results, see
[the mapping validation report](native-mapping-validation.md). Statements below
about outstanding dictionary displays describe this earlier stage, not the
current implementation.

## Scope and status

Validated on 2026-10-28 on Linux with Java 17 and Ant 1.10.15, using the
project's Java 8 source/target settings. Actual execution on Java 8, Windows
and macOS was not tested in this stage.

The native migration target is Python 3.15.2. It is **not yet achieved**.
This stage adds extended iterable assignment and list/tuple/set display
unpacking to the native ANTLR/AST/ASM/JVM pipeline. It does not redirect code
to CPython, replace the native standard library, or change the advertised
Python language version. The native version remains 2.7.5b2-DEV; compiled
module API version 43 records the new JVM runtime-helper dependency.

`org.python.util.jython` with the default runtime and `PythonInterpreter`
were used for native acceptance. `dist/cpython/bin/python3.15` was used only
for shared-test comparison. `jython3` is the optional CPython launcher, not
the native acceptance entry point.

## Results

| Check | Result |
| --- | --- |
| Fresh build in `build/native-unpacking/fresh` | Successful; 911 production and 139 Java test source files compiled |
| Native unpacking Python module | 42 cases passed, no skips |
| Shared module on CPython 3.15.2 | 35 passed, 7 JVM-specific cases skipped |
| Selected native Java tests | 18 passed, including 6 new unpacking cases |
| Related native Python regression | All 26 modules OK; includes the 42 new unpacking cases and the 114 earlier migration cases |
| Complete non-interactive Java driver, standard build layout | 54 discovered classes; 52 passed, 1 failed, 1 with no cases; 34,842 cases reported, 1 failure, no timeouts |
| Whitespace/error-marker check | `git diff --check` passed |

The Java driver follows the existing `javatest-built` candidate exclusions:
interactive ANTLR utilities, the two `jythonTest` classes and the abstract
`InterpTestCase` are excluded. Helper classes are not counted as tests.
`ConstructorSignatureTest` reports zero cases, not a pass of a test case.
The 18 selected Java cases also appear in the complete driver's totals and
must not be added to them as distinct coverage.

The new combination test exercises 144 before/after/input-length combinations
within one unittest case. Tests cover fresh and empty captures, nested and
chained targets, attributes/subscripts, partial assignment failures, loop and
comprehension targets, context managers, immediate iterable consumption,
hash and iterator failures, shadowed builtins, closure/nonlocal/global/class
scopes, default expressions, generator send/throw/close and receiver/index
suspension, AST round trips, AST subclasses and setter GC traversal, malformed
stars, unreachable errors, interactive incomplete input, Java collections,
Java arrays, Java Iterable objects and Java object identity.

No existing assertions or fixtures were removed or weakened for this stage.

## Reproduction

From the repository root, build the default layout:

```sh
ant jar copy-dev compile-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_unpacking.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest
python3 tests/cpython/run_jython_regression.py --reports build/native-unpacking/junit-default
```

The Python 3 driver in `tests/cpython` runs native JVM Java tests despite its
location. It does not select the optional CPython runtime. A host Python 3.9+
is sufficient to run the driver. It returns nonzero for the recorded indexer
failure below.

The 26-module Python command is recorded in
[the migration status](../PYTHON3_MIGRATION.md#build-and-test). A fresh native
build was also performed with:

```sh
java -Dbuild.dir=build/native-unpacking/fresh -cp 'build/tools/*' org.apache.tools.ant.Main jar copy-dev compile-test
```

The project-local Ant jars are ignored build tools, not repository dependencies;
an installed Ant can instead use `ant -Dbuild.dir=build/native-unpacking/fresh`.
Selected tests on that build used `build/native-unpacking/fresh/testclasses`
instead of `build/testclasses` and the newly produced `dist/jython-dev.jar`.

When an exact CPython 3.15.2 installation is available, run the comparison with:

```sh
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_unpacking.py -v
```

Raw logs from this workspace are under ignored `build/native-unpacking/`:

- `fresh-build.log` and `default-build.log` record the successful builds.
- `python-tests.log`, `java-tests.log` and `cpython-comparison.log` record the selected acceptance runs.
- `final-regression.log` records the final 26-module native Python regression.
- `full-java-default.log` and `junit-default/summary.json` record the complete Java result with the supported directory layout.
- `full-java.log` and `junit-direct/` retain the initial custom-layout Java run and its setup failures.

## Failures and corrections

The complete Java run using the default layout retains one failure:

```text
org.python.indexer.IndexerTest.testBasicDefsAndRefs
No reference to refs.foo at offset 266 of length 3
```

This exact failure was recorded before this unpacking stage. It was not
reproduced in the custom-layout run, but returned in the standard-layout run.
The dependence on layout/state has not been isolated; this is not a claim
that the defect is fixed or conclusively attributed to a historical baseline.
The 77 indexer cases include this one failure in the final report.

An initial attempt to run all Java tests against the fresh, nonstandard build
layout produced 19 failures across five classes. The proxy tests explicitly
write generated classes to `build/testclasses`, and the registry test derives
`dist` by walking two parents from the test-class directory. Merely replacing
the driver's classpath with a nested build directory violates those test setup
assumptions. Rebuilding in the standard directory and running the unmodified
driver resolved those five classes without source or assertion changes.

During implementation, ANTLR required an explicit operand label to avoid a
collision with its `expr` dynamic-scope stack. Expression collection was also
updated to accept the new parser-rule return types. Fresh builds and the
existing grammar/AST suites validate the resulting generated parser.

The legacy ASDL development generator required Python 3 syntax adaptation plus
its old `string.join`/`string.split` APIs in an isolated build-tool process.
Only the new AST class was copied from staging; the product interpreter and
standard library were not source-translated. Normal builds use the checked-in
Java AST and do not require those temporary tools.

Shared tests execute `exec`-mode compiled code via `eval(code, namespace)`, as
existing migration tests do, because the native runtime still has Python 2
`exec` statement restrictions. AST locations are keyword arguments, consistent
with the existing AST constructor API. Neither limitation was hidden by
changing production behavior outside this stage.

## Remaining acceptance gates

Full native Python 3.15.2 compatibility still requires the outstanding work in
[the migration status](../PYTHON3_MIGRATION.md#remaining-migration-work-and-boundaries).
In particular, strings/bytes, integers/division, iteration, classes/imports,
remaining syntax, deferred annotations, and the Python 3 standard library
remain unfinished. Dictionary/call/class-base generalized unpacking and
unpacking comprehensions are not implemented here. Length-hint callbacks are
not matched to CPython, and custom iterators still need the legacy `next`
method. Alternate bytecode/compiler-tooling paths are not comprehensively
migrated.

The native standard library is still based on `lib-python/2.7` and `Lib`.
A full native CPython 3.15.2 language/stdlib regression suite was not run and
would not yet be expected to pass. Passing this stage is not permission to
publish the native runtime as Python 3.15.2. That designation requires the
remaining language/object-model migration, modern library bootstrap, broad
version-specific acceptance, and maintained Java interoperability.
