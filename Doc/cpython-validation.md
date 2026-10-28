# CPython backend validation report

Validation date: 2026-10-28. Host: TencentOS 4, Linux x86-64, Java 17,
CPython 3.15.2 final (official-source private build), host Python 3.11.6.
See [backend usage](cpython-backend.md) for the architecture and install steps.

This report distinguishes passing acceptance tests from the broader regression
suites, which still have explicitly recorded failures. A skipped test is not a
pass. The CPython backend remains a separate process, not native JVM Python 3.

## Results

| Scope | Observed result |
| --- | --- |
| Final Ant `jar copy-dev compile-test` | Successful |
| Private runtime check | Exact CPython 3.15.2, 26 imports and matching build metadata |
| Installer offline tests | 14 passed |
| Original backend integration tests | 21 passed |
| Extended Java API / deployment / lifecycle tests | 26 passed |
| Python 3.15 and standard-library behavior tests | 23 passed |
| Native C extension / offline wheel tests | 5 passed |
| Original independent standard-library examples | 16 passed, 0 failed |
| First full CPython default run, seed 20261028 | 462 test files passed; 2 failed; 87 skipped; 9 resource-denied |
| Second full CPython default run after metadata repair, seed 20261029 | 463 test files passed; 1 failed; 87 skipped; 9 resource-denied |
| Additional decimal/subprocess/tzdata resource tests | 3 test files passed; runner: run=1,387, skipped=81 |
| Existing non-interactive Jython Java regression | 53 classes: 51 passed, 1 entirely ignored, 1 failed; JUnit reported 34,836 cases, 1 failure |

Both complete CPython runs selected 560 test files and took about 4 minutes
8 seconds. The second run's own summary is `run=50,875, skipped=2,775` test
cases and `run=551/560, failed=1, skipped=87, resource_denied=9` test files.
These are the runner's totals, **not a claim that 50,875 tests all passed**.
No failing test or assertion was removed from either complete run.

The full runs exercised the CPython build. After the final Java probe-cleanup
fix, the backend, extended lifecycle, language/library, native extension and
original smoke suites were rerun against the rebuilt JAR. The final Java
regression also used that build.

## Defects reproduced and fixed

### Missing build metadata

The original source installer used `make altinstall`. CPython 3.15.2's official
Makefile explicitly installs `build-details.json` only through `make install`.
Thus `test_build_details` reported 10 errors and 1 failure, despite ordinary
standard-library imports working.

The installer now runs `make install` inside its configured private prefix.
The existing private installation was repaired through that same official
target. Its post-install check now rejects missing or mismatched build metadata.
The upstream `test_build_details` file subsequently passed (17 cases reported,
7 skipped), as did the second complete run's metadata tests. A regression
asserts the installer selects the full install target rather than `altinstall`.
System Python and system packages were not changed.

### Launcher symlinks

Starting `jython3` through a symlink outside `dist/bin` previously failed to find
the JAR because `$0` referred to the symlink location. The wrapper now resolves
absolute and relative symlink chains, bounded to 40 links, unless an explicit
`JYTHON_HOME` is supplied. Tests cover an absolute symlink, a relative two-link
chain with Unicode/spaces, a PATH-based launch from another directory, and
explicit invalid-home rejection.

### JVM shutdown during version verification

The version probe starts before the execution-process shutdown hook exists.
Terminating the JVM during a slow probe left the probe process alive. The test
recorded that child's PID and reproduced the leak; it then killed only its own
recorded child for cleanup.

The probe now has its own JVM shutdown hook, unregistered on completion,
failure or interruption. The original failing test passes after rebuilding.
Additional tests cover Java-thread interruption during both probing and normal
execution, the 15-second probe timeout, and force-stopping an execution child
that ignores SIGTERM. SIGKILL cannot run shutdown hooks; this does not promise
supervision of grandchildren or arbitrary process trees.

## Remaining failures and controls

### CPython test_posixpath: host path collision

`test_realpath_invalid_paths` uses `/nonexistent/x\x00` and expects
`FileNotFoundError` for strict parent resolution. This host already has a real
`/nonexistent` directory containing application data. The directory predates
these runs. The expected missing parent is therefore present and CPython
correctly reaches the embedded NUL, raising `ValueError` instead.

This exact case fails both through `jython3` and through the CPython executable
directly. No Java backend is necessary to reproduce it. A separate regression
uses a guaranteed-missing parent under `TemporaryDirectory` and verifies the
corresponding str/bytes behavior for `strict=True`, `ALL_BUT_LAST`, `False` and
`ALLOW_MISSING`; it passes. The original upstream test remains unchanged and
its failure remains visible in the full report. `/nonexistent` was not deleted,
renamed or otherwise changed.

Direct reproduction:

```sh
dist/cpython/bin/python3.15 -I -B -m test -v \
  -m test_realpath_invalid_paths test_posixpath
```

### Native Jython indexer

`org.python.indexer.IndexerTest.testBasicDefsAndRefs` fails with:

```text
No reference to refs.foo at offset 266 of length 3
```

The other 76 cases in that class pass. A control recompiled the HEAD version of
`src/org/python/util/jython.java`, which has no CPython backend dispatch, into
an isolated directory and put it first on the classpath. The same indexer
failure remained. This is a limited entrypoint control, **not a complete
historical clean checkout build**. The indexer, parser and fixture were not
modified in this verification task; its failure remains open and is not
presented as a passing Java regression suite.

### Test-harness issues corrected

The installed Ant lacked its optional JUnit task. Fetching optional artifacts
was unsuccessful, so existing Java tests were run using the repository's own
JUnit 4.10 JAR, with the same source candidate/exclusion rules as `javatest-built`.
The discovery helper filters non-test and abstract helper classes, and each
concrete class executes in a separate JVM with a timeout and its own log.

The first direct driver inherited stdin, which caused the JSR223 debugger EOF
test to wait for input. Setting stdin to `DEVNULL`, as appropriate for this
non-interactive test, made all 25 `ScriptEngineTest` cases pass. This was a
driver problem, not a product fix. The final full Java run has no timeout.
`ConstructorSignatureTest` is entirely ignored by JUnit and is recorded as
`no_cases`, not counted as a passed class. Detailed exclusions and helper names
are present in the driver's JSON summary.

## Reproduce

From the repository root, after installing the private runtime:

```sh
ant jar copy-dev compile-test
python3 -B tools/install_cpython.py --check-only
python3 -B tests/cpython/test_installer.py -v
python3 -B tests/cpython/test_backend.py -v
python3 -B tests/cpython/test_backend_extended.py -v
dist/bin/jython3 -B tests/cpython/test_stdlib.py -v
dist/bin/jython3 -B tests/cpython/test_native_extension.py -v
dist/bin/jython3 -B Demo/python3_stdlib_smoke.py
```

The extended suite compiles a Java API client using Java 8-compatible source.
It exercises 16 concurrent builders, 12 concurrent CLI requests with distinct
environments, 4 MiB binary stdin, simultaneous 4 MiB stdout and stderr,
byte-exact Java/Python pipes, builder cwd/environment customization, repeated
`run()` calls without JVM exit, configuration refresh and rejection, UTF-8 under
the C locale, package-relative imports and zipapps. It is not a benchmark or a
long-duration soak test.

Native tests compile a small trusted C module using the installed Python headers
and sysconfig flags. They check the compiled header version, callable C APIs and
argument errors, import the extension in another process, build a native wheel,
and install/import that wheel in a temporary venv with `pip --isolated
--no-index --no-deps`. No PyPI download or system installation is performed.

Complete default CPython regression:

```sh
mkdir -p build/cpython-validation/full-temp
dist/bin/jython3 -E -B -Wd -m test -j4 -r --timeout=180 \
  --randseed=20261029 \
  --tempdir="$PWD/build/cpython-validation/full-temp" \
  --junit-xml="$PWD/build/cpython-validation/full-final.xml" \
  > build/cpython-validation/full-final.log 2>&1
```

Additional offline resources:

```sh
dist/bin/jython3 -E -B -m test -j2 \
  -u decimal,subprocess,tzdata --timeout=180 \
  test_decimal test_subprocess test_zoneinfo
```

Existing non-interactive Java regressions, without optional Ant JUnit tasks:

```sh
python3 -B tests/cpython/run_jython_regression.py \
  --reports=build/cpython-validation/junit-final
```

These last broad commands return nonzero on the known failures described above.
Do not interpret the presence of a report file as a successful test run.

## Artifacts and limits

Raw logs, full-suite XML, before/after failure reproductions and Java JSON
summaries are under `build/cpython-validation/`, an ignored build-output tree.
Key files are `full.log`, `full-final.log`, `full-final.xml`,
`build-details-fixed.log`, `posixpath-direct.log`, `shutdown-before.log`,
`extended-final.log`, `extra-resources.log`, `native-final.log`,
`indexer-baseline.log` and `junit-final/summary.json`. Generated runtime binaries
and logs are not source-controlled deliverables; the scripts above reproduce
them. Ant `clean` can remove these outputs.

Tests ran only on this Linux/Java 17 host. Windows, macOS, an actual Java 8 JVM,
GUI, external network integration, very large files, sanitizer/debug builds,
reference-leak checks, free-threaded builds and long-duration load were not
validated. Default CPython skips include OS-specific, GIL-disabled-only,
build-tool-dependent and unavailable GUI tests. `_tkinter` is still absent in
this private build. The extra resource run enables only decimal, subprocess and
tzdata, not all optional resources. Passing a custom native wheel is not a claim
that all third-party packages already support CPython 3.15.
