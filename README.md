# Jython: Python for the Java Platform
[![Maven Central](https://maven-badges.sml.io/maven-central/org.python/jython-standalone/badge.svg)](https://search.maven.org/artifact/org.python/jython-standalone/)
[![Javadocs](https://www.javadoc.io/badge/org.python/jython-standalone.svg)](https://www.javadoc.io/doc/org.python/jython-standalone)
[![APIdia](https://apidia.net/java/Jython/badge.svg)](https://apidia.net/java/Jython)

This is the development repository of Jython,
the implementation of Python in Java.
The native JVM runtime is still based on Python 2.7, with Python 3.15.2 as its
migration target. This checkout also offers an optional CPython 3.15.2 process
backend, described below.

This working tree contains an experimental, native Python 3 migration:
function annotations, keyword-only and positional-only parameters, `nonlocal`,
exception chaining (`raise ... from ...`), PEP 498 f-strings with debug fields,
extended assignment unpacking, iterable unpacking in list/tuple/set displays,
dictionary `**mapping` displays, generalized multiple `*args`/`**kwargs`
function calls, iterable class bases such as `class C(*bases, Other, *more)`,
and expression decorators such as `@decorators[0]` or `@a if enabled else b`.
Call expansion preserves Java interoperation and rejects duplicate keywords
rather than overwriting them. Decorators use the existing native expression
language; assignment expressions, matrix multiplication and `async`/`await`
remain unsupported. Class-header keywords and the full Python 3 metaclass
protocol are not implemented.
It is **not a complete Python 3 implementation**; the runtime and standard library
are still based on Python 2.7. Python 3.12's PEP 701 f-string extensions are not
implemented. Some Python 2 behaviors deliberately change, including closure-cell
deletion and restoration of exception state when leaving a handler. See
[migration status](PYTHON3_MIGRATION.md) for the supported subset, build commands,
tests, compatibility boundaries, and remaining work.

## Optional CPython 3.15.2 backend

For Python 3.15.2 applications, this checkout can launch an actual, private
CPython interpreter as a separate process. With native build dependencies
installed, run:

```sh
python3 -B tools/install_cpython.py
ant jar copy-dev
dist/bin/jython3 -B Demo/python3_stdlib_smoke.py
```

Alternatively configure `JYTHON_CPYTHON_EXECUTABLE` to an existing CPython
3.15.2 final executable. See [installation and Java integration](Doc/cpython-backend.md)
for dependencies, version checks, command-line options and acceptance tests.
This is not native JVM Python 3 or JNI embedding: `PythonInterpreter`, `PyObject`
and direct `import java` interoperation remain on the original Jython path.
The default `jython` command is unchanged; `jython3` selects CPython explicitly.

## Compatibility

Jython provides good compatibility with Python 2.7 *the language*.
Also, a high proportion of the standard library is included,
taken from late versions of CPython (around 2.7.13).
Some standard library modules have a Jython-specific implementation
that has not kept pace with its CPython counterpart.

Jython 2.7 support for the Python ecosystem
includes built-in support of *pip/setuptools*.
You can use `bin/pip` if the targets do not include `C` extensions.
There is a native launcher for Windows (`bin/jython.exe`)
that works essentially like the `python` command.

Jim Baker presented a talk at PyCon 2015 about Jython 2.7,
including demos of new features: https://www.youtube.com/watch?v=hLm3garVQFo

## Support

Python 2.7 (the language) is no longer supported by the PSF.
Running on Jython should not be considered an alternative to porting your
application to Python 3, due to the limitations cited here
and the small amount of effort available to support 2.7.x.
Jython 2.7 is offered for continuity because a 3.x is not yet available.

See [ACKNOWLEDGMENTS](ACKNOWLEDGMENTS) for details about Jython's copyright,
license, contributors, and mailing lists.
Consult [NEWS](NEWS) for detailed release notes, including bugs fixed,
backward breaking changes, and new features.
We sincerely thank all who contribute to Jython, by bug reports, patches,
pull requests, documentation changes and e-mail discussions.

## Downloads

Binary downloads are available from https://www.jython.org/download
along with Maven and Gradle dependency information.

## How to build Jython

The project uses Git for version-control,
and the master repository is at https://github.com/jython/jython,
You should clone this repository to create a buildable copy of the latest state
of the Jython source.
Start a new branch for any bug-fix or experimentation you plan.

The previously authoritative repository at https://hg.python.org/jython is not now in use,
remaining frozen at v2.7.2.

### Build using `ant` for development

Jython is normally built using `ant`.
It is necessary to have Ant and at least a Java 8 SDK on the path.
To build Jython in development, we generally use the command:
```
ant
```
This leaves an executable in `dist/bin`
that you may run from the check-out root with:
```
dist/bin/jython
```
Other `ant` targets exist, notably `clean`, `javatest` and `jar`.

You can test your build of Jython (by running the regression tests),
with the command:
```
dist/bin/jython -m test.regrtest -e -m regrtest_memo.txt
```
or by invoking the Ant target `regrtest`.

### Build an installer using `ant`

If you want to install a snapshot build of Jython, use the command:
```
ant installer
```
This will leave you with a snapshot installer JAR in `dist`,
that you can run with:
```
java -jar jython-installer.jar
```
for the graphical installer, or:
```
java -jar jython-installer.jar --console
```
For the console version. (A `--help` option gives you the full story.)

### Build a JAR using Gradle

We have a Gradle build that results in a family of JARs and a POM.
This is intended to provide the Jython core in a form that Gradle and Maven
users can consume as a dependency.
Invoke this with:
```
PS> .\gradlew publish
```
and a JAR and POM are delivered to ` .build2\repo` 

Whereas the JARs delivered by the installer are somewhat "fat",
embedding certain dependencies in shaded (renamed) form,
the JAR from the Gradle build is "spare"
and cites its dependencies externally through a POM.

## Other Useful Documentation

[Project Processes](ProcessDocs)

