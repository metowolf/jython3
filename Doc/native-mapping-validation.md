# Native mapping-display validation

## Scope

This stage follows [native iterable unpacking](native-jvm-validation.md) and
adds `{**mapping, key: value, **other}` directly to the native ANTLR/AST/ASM/JVM
compiler. The native migration target remains Python 3.15.2, but the complete
runtime and standard-library migration is **not finished**.

The compiler now uses a null key slot in the existing `Dict` AST to represent
mapping expansion. Generated code calls `UnpackingSupport.mergeMapping` and
preserves intermediate dictionaries and key/value arrays across generator
suspension. Compiled-module API **44** prevents older runtimes from loading
code that depends on this new method. The advertised Python language version
remains 2.7.5b2-DEV.

Native acceptance uses `org.python.util.jython` without the CPython runtime
property, or `PythonInterpreter` directly. Only shared-test comparison uses
`dist/cpython/bin/python3.15`. No native test is counted as passing merely
because it passes on CPython.

## Acceptance

Validation environment: Linux, Java 17, Ant 1.10.15, using the project's Java 8
source/target settings. This is not validation on an actual Java 8 JVM or on
Windows/macOS.

| Check | Result |
| --- | --- |
| Standard build | Successful |
| Fresh build in `build/native-mapping/fresh` | Successful; 911 production and 140 Java test source files compiled |
| New native mapping Python module | 42 cases passed, no skips |
| Shared module on CPython 3.15.2 | 34 cases passed, 8 JVM-specific cases skipped |
| Selected native Java classes | 24 cases passed on both standard and fresh builds, including 6 new mapping cases |
| Broad native Python regression | All 33 modules OK after building the test JAR; includes 198 cases across the six migration modules |
| Complete non-interactive Java driver | 55 discovered classes; 53 passed, 1 failed, 1 with no cases; 34,848 cases reported, 1 failure, no timeouts |
| Final diff check | `git diff --check` passed |

The selected Java cases also occur in the complete-driver totals. The driver
retains the existing candidate/exclusion rules described in the earlier
validation report; it is not every possible interactive/platform test.
`ConstructorSignatureTest` has no discovered cases and is not counted as a
passing case.

Coverage includes empty/fresh shallow copies, multiple and interleaved merges,
last-value-wins duplicates, non-string and `None` keys, ordinary `None` values,
nested displays, conditional/lambda operands, mapping protocol side effects,
key iterator exhaustion, live exact key lists, dict subclass dispatch, failure
propagation, literal expression ordering, shadowed builtins, scopes/defaults,
generator send/throw/close, nested suspension, manual AST construction,
invalid/unreachable targets, interactive partial input, Java maps, native
namespaces, and Java object identity. Larger cases exercise 80 consecutive
literal entries and 80 mapping operands.

## Reproduction

From the repository root:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_mapping_unpacking.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest
python3 tests/cpython/run_jython_regression.py --reports build/native-mapping/junit-default
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_mapping_unpacking.py -v
```

The last command requires the optional exact CPython 3.15.2 installation; the
native implementation does not. The Java driver uses a host Python 3.9+ only
to orchestrate JVM tests, despite its location under `tests/cpython`.

For the broad native Python regression:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration
```

The fresh build used `-Dbuild.dir=build/native-mapping/fresh`. Its native tests
used that directory's `testclasses` and the newly produced `dist/jython-dev.jar`.
The complete Java driver used the standard `build/classes`, `build/exposed`
and `build/testclasses` layout from the successful standard build of the same
sources, since several legacy tests hard-code that layout.

Raw logs are retained in ignored `build/native-mapping/`:

- `baseline.log` shows the preceding build rejected `{**{}}` with a syntax error.
- `build.log`, `fresh-build.log` and `test-jar-build.log` record successful builds.
- `python-tests.log`, `java-tests.log`, `fresh-java-tests.log` and `cpython-comparison.log` record targeted acceptance.
- `regression.log` retains the initial broad run and its missing-test-JAR failure; `final-regression.log` records all 33 modules passing after building that dependency.
- `full-java.log` and `junit-default/summary.json` record the complete Java results.

## Issues found

The old target checks accepted a dictionary display as an assignment target.
The new negative case exposed this problem. Parser and scope checks now reject
dictionary displays in assignments, augmented assignments, deletions, loops,
comprehensions and context-manager targets, including hand-built ASTs and
unreachable statements. Dictionary receivers of subscript targets remain valid.
No test assertion was weakened to make these checks pass.

The first broad run passed 32 modules but failed `test_java_integration` because
its separate JVM could not find `javatests.ProxyDeserialization`. That test uses
`dist/jython-test.jar`, not the parent process's loose test classes. The standard
`jar-test` target generates this required artifact; no production code or
integration-test source was changed to address the setup failure. After building
that artifact, the complete rerun reported `All 33 tests OK.` Existing Security
Manager deprecation and logging-permission warnings remained visible but did
not cause a test failure.

The complete Java run retains the previously reported failure:

```text
org.python.indexer.IndexerTest.testBasicDefsAndRefs
No reference to refs.foo at offset 266 of length 3
```

The 77 indexer cases include that failure. It is not fixed by this stage and
has not been conclusively attributed to a clean historical baseline.

## Compatibility boundaries

Dictionary display expansion is not a Python 3 dictionary-object migration.
The existing native `dict` still does not guarantee insertion order. Modern
views, cached hash reuse, exact hash/equality callback counts, large-literal
allocation strategies and concurrent mutation behavior are not matched to
CPython. Tests intentionally do not assert an ordering guarantee that the
runtime does not provide.

Generic mappings must have callable `keys()` returning an iterable and support
item lookup. Iterators still follow the native legacy `next` protocol and do
not gain full modern length-hint behavior in this stage. Mapping errors retain
native wording where it differs from CPython.

Generalized multiple function-call unpacking, starred class bases, unpacking
comprehensions, the remaining language/object-model migration, and the modern
standard library remain outstanding. See
[the migration status](../PYTHON3_MIGRATION.md) for the complete boundary list.
No complete CPython 3.15.2 suite has passed on the native runtime, and no such
claim is made here.
