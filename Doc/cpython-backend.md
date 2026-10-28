# CPython 3.15.2 execution backend

This checkout offers an **opt-in, separate-process CPython 3.15.2 backend**.
It runs the actual CPython interpreter with its own Python 3.15 standard library
and native extensions. It does not translate Python source to Python 2 or copy
Python 3 modules into Jython's `Lib` directory.

The default Jython CLI and `PythonInterpreter` remain the experimental JVM
interpreter based on 2.7. They do not become Python 3 interpreters. This backend
is not JNI embedding, does not share Python/Java objects, and does not support
Jython's `from java...` imports. Keep those programs on the Jython path, or
explicitly design an IPC interface. Existing Java embedding APIs are unchanged.

## Install

Requirements: a Java 8+ JDK for Jython, Apache Ant, and either an existing
**CPython 3.15.2 final** installation or the source installer below. Other patch
versions, prereleases, and PyPy are rejected rather than silently substituted.

For an existing CPython, set its executable path (not a shell command):

```sh
export JYTHON_CPYTHON_EXECUTABLE=/absolute/path/to/python3.15
ant jar copy-dev
```

For a private source build on Linux/macOS, first provide Python 3.9+, a C
compiler, `make`, and the development libraries for OpenSSL, zlib, bzip2, xz,
SQLite, libffi, readline/ncurses, zstd and mpdecimal. GDBM, UUID and Tcl/Tk enable
additional platform features. The installer does not install operating-system
packages or use elevated privileges. Debian-family package names include
`build-essential`, `libssl-dev`, `zlib1g-dev`, `libbz2-dev`, `liblzma-dev`,
`libsqlite3-dev`, `libffi-dev`, `libreadline-dev`, `libncurses-dev`, `libzstd-dev`,
`libmpdec-dev`, `libgdbm-dev`, `uuid-dev` and `tk-dev`. RPM-family systems use the
corresponding `*-devel` packages, including `mpdecimal-devel`. On macOS, configure
`CPPFLAGS`, `LDFLAGS` and `PKG_CONFIG_PATH` for libraries outside the system
search paths as needed.

```sh
python3 -B tools/install_cpython.py --jobs 4
ant jar copy-dev
```

The source installer downloads the official `Python-3.15.2.tar.xz`, verifies a
pinned SHA-256 digest, and rejects links, path traversal and special archive
members. Its source is https://www.python.org/ftp/python/3.15.2/; the digest
comes from the archive's published `.sigstore` metadata. Hash verification is
not a claim that this script verifies the Sigstore signature itself.

The download cache and build tree are under `build/`. Installation is under
`dist/cpython/`, with executable `dist/cpython/bin/python3.15`. No system Python
is replaced and no global pip is changed. `make install` installs CPython's
standard library, native extensions, regression tests, bundled pip and official
`build-details.json` into this **private prefix**. Python/pip aliases are also
created only inside that prefix. Do not choose a system prefix for this private
installer. Unlike `altinstall`, the full install target includes build metadata.
An isolated post-install check requires 26 common standard-library imports,
including `_decimal`, `ssl`, `sqlite3`, `ctypes`, `bz2`, `lzma`, `compression.zstd`,
`readline` and `venv`, and verifies the build metadata matches the runtime.
Missing native dependencies or metadata fail the installation check.

`--prefix`, `--cache-dir`, and `--work-dir` select alternative paths. Existing
interpreters are checked rather than overwritten. An incomplete or invalid
installation is reported, not silently accepted. To rebuild after fixing
missing dependencies, use a new empty prefix and work directory, then configure
`JYTHON_CPYTHON_EXECUTABLE` to that prefix's `bin/python3.15`. An existing verified
archive is reused without downloading. `--check-only` checks the installed
runtime without building. Keep the archive and working directories trusted.
If a previous private build used `altinstall`, rerun `make install` in its
existing, private-prefix-configured build tree to restore build metadata, then
run `--check-only`. Alternatively create a fresh private installation.

The source installer is POSIX-only. On Windows, install official CPython 3.15.2
with the standard library and required optional components and configure its
`python.exe` explicitly. The Java launcher is portable; this checkout's
`jython3` shell wrapper is POSIX-only. Linux binaries are not Windows or macOS
artifacts. The source-built runtime is not bundled inside the JAR; deploy it
and its native library dependencies separately. Ant `clean` may remove `dist`
and `build`, including a default private runtime.

## Run Python 3

From a built checkout:

```sh
dist/bin/jython3 -V
dist/bin/jython3 -c 'import sys; print(sys.version); print(sys.implementation.name)'
dist/bin/jython3 -B Demo/python3_stdlib_smoke.py
dist/bin/jython3 -m venv build/example.venv
build/example.venv/bin/python -m pip --version
```

`jython3` intentionally ignores `JYTHON_OPTS`. Python command-line arguments,
including `-c`, `-m`, `-I`, `-X`, script files and `-`, are forwarded unchanged.
Do not pass Jython-specific `-J`, `-D`, `-Q` or `-jar` options to `jython3`.
`JYTHON_HOME` selects the directory containing the built JAR, and `JAVA_HOME`
selects Java. The wrapper resolves absolute/relative launcher symlinks using
`readlink` when `JYTHON_HOME` is not set; an explicit home always wins.
No shell is used to run Python code or interpret its arguments.

The existing Java CLI also supports an explicit backend selection:

```sh
java -Dpython.runtime=cpython -Dpython.home=dist \
  -cp 'dist/jython-dev.jar:extlibs/*' org.python.util.jython \
  -B Demo/python3_stdlib_smoke.py
```

Here `-Dpython.runtime=cpython` is a **JVM property before the Java class**, not
a Python option. Omitting it preserves the native Jython path; unknown values
are errors. With the existing Jython shell wrapper use
`dist/bin/jython -J-Dpython.runtime=cpython ...`. Properties supplied to an
embedded `PythonInterpreter` do not select this backend.

For the direct CPython launcher, only the Jython JAR is needed:

```sh
java -Dpython.cpython.executable=/absolute/path/to/python3.15 \
  -cp dist/jython-dev.jar org.python.util.CPythonLauncher -m pip --version
```

Executable lookup is: JVM `python.cpython.executable`, then environment variable
`JYTHON_CPYTHON_EXECUTABLE`, then `cpython/bin/python3.15` under `python.home`
(or next to the JAR). The Windows default is `cpython/python.exe`. A configured
path may point to a CPython 3.15.2 virtual environment. There is no PATH-based
fallback to an unrelated interpreter. Bare class-directory development runs
without `python.home` look under `./dist`.

The version probe uses `-I -S`, has a 15-second timeout and runs before user
code. Script execution has no launcher-imposed timeout. stdin/stdout/stderr
and the working directory are inherited, and Python exit codes are returned.
Launcher/configuration errors return 2; interrupted Java waits return 130.
JVM shutdown hooks protect both the version probe and the direct execution
child, terminating and force-stopping them if necessary. Probe hooks are removed
on success, error or interruption. SIGKILL cannot run JVM shutdown hooks.
This is not a process-tree supervisor: applications must manage grandchildren
and external daemons. OS process-group signal behavior and interactive terminal
handling can vary by platform; in-process JVM signals are not Python signals.

To avoid mixing libraries, `PYTHONHOME`, `PYTHONPATH` and `PYTHONSTARTUP` are
removed from the child environment. `JYTHONPATH` has no meaning to CPython.
For intentional CPython-only additions use `JYTHON_CPYTHON_PYTHONPATH`, mapped
to the child's `PYTHONPATH`. Other CPython environment options are preserved,
and normal CPython `-E`/`-I` rules apply. This is **not a security sandbox**;
normal site-packages and user code can execute unless you choose isolated mode.

## Java integration

For simple inherited-I/O execution, use `CPythonLauncher.run(args)`; unlike
`main`, it returns an exit code rather than terminating the JVM.

For captured output or a custom working directory, use `processBuilder`:

```java
import java.io.File;
import org.python.util.CPythonLauncher;

System.setProperty("python.cpython.executable", "/absolute/path/to/python3.15");
ProcessBuilder builder = CPythonLauncher.processBuilder(
        "-c", "import json; print(json.dumps({'answer': 42}))");
builder.redirectErrorStream(true);
builder.redirectOutput(new File("python-result.json"));
Process child = builder.start();
child.getOutputStream().close();
int exitCode = child.waitFor();
```

This builder uses pipes by default and verifies the interpreter first. Its
caller owns stream consumption, timeout and cleanup. It is not a replacement
for `PythonInterpreter.eval()`, `PyObject`, callbacks or direct Java imports.
Use an explicit protocol such as JSON when exchanging data between processes.

## Acceptance and scope

```sh
python3 -B tools/install_cpython.py --check-only
python3 -B tests/cpython/test_installer.py -v
python3 -B tests/cpython/test_backend.py -v
python3 -B tests/cpython/test_backend_extended.py -v
dist/bin/jython3 -B tests/cpython/test_stdlib.py -v
dist/bin/jython3 -B tests/cpython/test_native_extension.py -v
dist/bin/jython3 -B Demo/python3_stdlib_smoke.py
```

Extended API tests require a JDK. Native extension tests require the POSIX C
compiler used by CPython; they compile a small test module and install its wheel
into a temporary virtual environment entirely offline. All generated native
artifacts and virtual environments are temporary.

For full CPython runs and existing Jython Java regressions, see the
[detailed validation report](cpython-validation.md), including known failures
and exact reproductions. The Java regression driver uses the repository's
existing JUnit dependency when Ant's optional JUnit task is unavailable.

A targeted selection of the installed CPython regression suite can also be run:

```sh
dist/bin/jython3 -B -m test -j2 --timeout=120 \
  test_csv test_io test_pathlib test_statistics test_urlparse test_queue \
  test_datetime test_functools test_sqlite3 test_asyncio test_ssl
```

Run backend tests with host Python 3.9+; a host version other than 3.15.2 also
exercises rejection of a wrong runtime. `JYTHON_TEST_CLASSPATH` can select another
built JAR. For the Gradle artifact use the Java launcher class and an explicitly
configured CPython executable; Gradle still packages the original Jython 2.7
library for the native JVM path and does not install CPython.

The acceptance suite covers Python 3 core semantics, deferred annotations,
pattern matching, exception groups, template strings, Python 3.15 unpacking,
`frozendict`, `sentinel`, lazy imports, async tasks, CSV text I/O, SQLite
transactions, TLS configuration, compression, `ctypes`, time zones, sockets and
multiprocessing. CLI tests cover argument preservation, binary I/O, files,
modules, exit codes, environment isolation, venv/pip, default Jython behavior,
version rejection and direct-child cleanup.

These checks do not constitute a pass of the entire CPython regression suite or
all possible native modules. Standard-library availability follows the selected
CPython build and OS: `tkinter`, platform-specific modules, time-zone data and
other optional native dependencies may need additional installation. Third-party
C extensions require wheels/builds for the actual CPython version, ABI and OS;
Jython's old packages and CPython 3.11 binary wheels are not reusable as-is.

### Workspace validation (2026-10-28)

Verified on TencentOS 4 x86-64 with Java 17 and an official-source CPython 3.15.2
build. Native development headers were unpacked from matching RPMs into an
ignored workspace SDK; system packages and the system Python were not changed.

| Check | Result |
| --- | --- |
| Ant `jar copy-dev compile-test` | Successful |
| Installation dependency checks | 26 imports and build metadata passed |
| Installer safety tests | 14 passed |
| Backend integration tests | 21 passed |
| Extended Java API / process / deployment tests | 26 passed |
| Python 3.15 and standard-library acceptance | 23 passed |
| Native C extension and offline wheel installation | 5 passed |
| Original Python 3 standard-library examples | 16 passed, 0 failed (previous native Jython result: 7/16) |
| Existing Java function / exception-chain / f-string regression | 12 passed |
| Targeted CPython upstream suite above | SUCCESS: 51 test files passed; 2 Windows-only files skipped; runner totals: run=8,412, skipped=526 |
| Full default CPython suite, two seeds | Second run: 463 files passed, 1 environment-dependent failure, 87 skipped, 9 resource-denied; run=50,875, skipped=2,775 |
| Extra decimal / subprocess / tzdata resources | 3 files passed; run=1,387, skipped=81 |
| Existing non-interactive Java regression | 34,836 cases reported, 1 indexer failure; 51 classes passed, 1 entirely ignored, 1 failed |

The complete default suite is **not entirely green** on this host: the one
remaining `test_posixpath` error assumes `/nonexistent` does not exist, but this
host already has that directory. Direct CPython reproduces the same error;
an equivalent regression using a guaranteed-missing temporary path passes.
No system directory or upstream assertion was changed to hide the failure.
See the detailed report for the separate native Jython indexer failure, also
reproduced with the HEAD version of the CLI entrypoint as a control. That control
is not a full historical checkout test.

The installed build lacks `_tkinter` because Tk development/runtime dependencies
were not installed. Thus Tk GUI modules (including Tk-based tools) are not
supported by this particular build. The other unavailable entries found via
`sys.stdlib_module_names` are Windows/macOS-specific modules, not missing Linux
implementations. This is not a claim of all-platform or full-suite compatibility.
