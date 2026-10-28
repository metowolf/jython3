# Python 3 migration status

## Status

The goal is a complete Python 3 migration. That goal is **not complete**.
This working tree implements native function-syntax, nonlocal-scope,
exception-chaining, and f-string stages on the existing Jython 2.7 runtime.
It is not Jython 3, is not a Python 3 compatibility mode, and does not make
arbitrary Python 3 packages runnable.

The project version remains 2.7.5b2-DEV. The bundled library is still based on
`lib-python/2.7` and `Lib`. Python 2 syntax is deliberately retained during
migration so that the bundled library can continue to load. Some runtime
behaviors now follow Python 3 rather than Python 2; see the boundaries below.
No whole-language Python 3 minor-version compatibility is advertised. The
implemented signatures include Python 3.0 syntax and positional-only syntax
from Python 3.8.

The application execution target is now **CPython 3.15.2 final**, available via
an optional [separate-process backend](Doc/cpython-backend.md). Use `jython3` or
`-Dpython.runtime=cpython` on the Java CLI to select it. This runs real CPython
with its own standard library; it does not upgrade the native runtime described
in this document. `PythonInterpreter` and direct Java imports retain their
existing JVM behavior. Native migration work below remains outstanding.

## Implemented function syntax

| Feature | Behavior |
| --- | --- |
| `def f(a: T) -> R` | Parameter and return expressions are evaluated in the defining scope and stored in `__annotations__`. Annotations do not enforce types. |
| `def f(*, required, option=value)` | Required and defaulted keyword-only parameters are bound and validated at call time. |
| `def f(*args, option=value, **kwargs)` | Extra positional and keyword arguments occupy separate parameter slots. |
| `def f(a, /, b)` | Parameters before `/` cannot be bound by a keyword. A same-named keyword may still enter `**kwargs`. |
| `lambda a, /, *, option=value: ...` | The same parameter binding rules apply, without parameter or return annotations. |
| Function metadata | `__kwdefaults__`, `__annotations__`, `co_posonlyargcount`, and `co_kwonlyargcount` are exposed. `co_argcount` includes only positional parameters. |

```python
def multiply(value: int, /, *, scale: int = 2) -> int:
    return value * scale

assert multiply(3) == 6
assert multiply(3, scale=4) == 12
assert multiply.__kwdefaults__ == {'scale': 2}
assert multiply.__annotations__ == {'value': int, 'scale': int, 'return': int}
```

Function decorator expressions are evaluated top-to-bottom before defaults.
Positional defaults, keyword-only defaults, parameter annotations, and the return
annotation are then evaluated, in that order. Decorators are applied
bottom-to-top after the new attributes are attached to the function.
Defaults are evaluated once per definition, not once per call.

`__kwdefaults__` accepts a dictionary or `None`; deleting it removes the defaults.
`__annotations__` accepts a dictionary or `None`; reading it after deletion or
assignment of `None` creates an empty dictionary. Both participate in garbage
collection traversal. Fixed-arity calls, argument-array calls, bound methods,
closures, generators, and Java functional-interface calls use the new binding
information.

## Implemented nonlocal scope

`nonlocal` has its own AST node and binds the nearest enclosing function's
existing variable. Reads, assignments, augmented assignments, imports,
definitions, and deletion operate on the shared closure cell. Class namespaces
are skipped when locating a binding; a class body nested in a function can itself
use `nonlocal`. Intermediate closures and suspended generators retain the cell.

```python
def counter():
    value = 0
    def increment():
        nonlocal value
        value += 1
        return value
    return increment

increment = counter()
assert increment() == 1
assert increment() == 2
```

Static checks reject module-level declarations, missing outer bindings,
parameter/global conflicts, and declarations following use or assignment.
An outer binding may appear later in the source or in a conditional branch.
Unreachable declarations are still checked. An intervening function's `global`
declaration prevents binding through it. Repeated declarations before use are
allowed. `keyword.iskeyword('nonlocal')` recognizes the new keyword.

Deleting a local variable captured by a closure is now allowed, unlike Python 2.
Accessing an empty local cell raises `UnboundLocalError`; accessing an empty
outer/free cell raises `NameError`. Deleted cells may subsequently be rebound.
The identifier-list adapter and statement AST subtype constructor were also
corrected so direct construction and Python subclasses of `ast.Nonlocal` work.

## Implemented exception chaining

`raise exception from cause` evaluates both expressions before constructing any
exception classes. Causes may be Python exception instances, exception classes,
or `None`. It is distinct from the retained Python 2 comma-form raise;
combining the two forms is rejected, including in manually constructed ASTs.

```python
try:
    try:
        raise ValueError('invalid value')
    except ValueError as original:
        raise RuntimeError('operation failed') from original
except RuntimeError as error:
    assert isinstance(error.__cause__, ValueError)
    assert error.__context__ is error.__cause__
    assert error.__suppress_context__ is True
```

Python `BaseException` instances expose `__cause__`, `__context__`,
`__suppress_context__`, `__traceback__`, and `with_traceback()`. Assignments are
validated; exception and traceback references participate in GC traversal.
Setting `__cause__`, including assigning `None`, suppresses context display.
`raise ... from None` retains the actual implicit context but hides it in output.

Implicit context follows the dynamically active handler, including exception
paths through `finally` and a context manager's `__exit__`. Handler state is
restored on normal exit, return, break, continue, or exception propagation.
Frames retain their own handler state across generator suspension, and resumed
generators inherit their current caller's state when they have no handler of
their own. Exceptions injected by `throw()` use the generator's active handler.
A bare `raise` uses the active exception; without one it raises `RuntimeError`.

Native exception display and the `Lib/traceback.py` override show the cause first,
or otherwise the unsuppressed context, with Python 3 chain separators. Formatting
uses identity-based cycle protection and iterative traversal for long chains.
The traceback formatting/printing entry points accept `chain=False` to omit
chaining. Existing stack and syntax-error formatting are retained.

`sys.exc_info()` no longer deliberately retains an exception after its handler
finishes. `Lib/doctest.py` now uses the exception tuple captured inside the
handler rather than retrieving it again after the handler has exited.

## Implemented f-strings

The native parser accepts PEP 498 f-string syntax (Python 3.6) and debug fields
from Python 3.8, subject to the existing expression-language/runtime boundaries.
Python 3.12's PEP 701 extensions are **not** implemented.

| Feature | Behavior |
| --- | --- |
| `f'{expression}'`, `F"..."` | Fields are native expression ASTs, evaluated in the surrounding scope. |
| `fr'...'`, `rf'...'` | All case combinations work; literal backslashes stay raw, while braces still delimit fields. |
| Single, double and triple quotes | Multiline literals and multiline expressions inside triple quotes are accepted. |
| `{{` and `}}` | Produce literal braces outside replacement fields. |
| `!s`, `!r`, `!a` | String, representation and ASCII-escaped representation conversions precede formatting. |
| `f'{number:08.2f}'` | Uses the existing `__format__` protocol, including numeric, text and datetime formatting. |
| `f'{number:{width}.{precision}f}'` | Nested fields supply dynamic format specifications. |
| `f'{value=}'` | Preserves expression text and whitespace; defaults to `!r` unless an explicit format specification is present. |
| Adjacent literals | Text literals and f-strings concatenate; explicit bytes literals cannot be mixed with f-strings. |

```python
from datetime import datetime, timedelta

now = datetime.now()
print(f"Current time: {now}")
print(f"Formatted: {now:%Y-%m-%d %H:%M:%S}")
print(f"In three days: {(now + timedelta(days=3)).strftime('%Y-%m-%d')}")
value, width, precision = 12.3456, 9, 2
assert f'{value:{width}.{precision}f}' == '    12.35'
assert f'{value=:.2f}' == 'value=12.35'
```

Fields are evaluated once, left to right. Each field's value and nested format
fields are evaluated before its conversion and `__format__` call. No global
`format`, `str`, `repr`, `ascii`, or runtime `eval` call is used. Local variables,
closure cells, `nonlocal` use checks, default arguments, class bodies and
suspension with `yield` use the normal compiler and frame machinery. Exceptions
stop subsequent field evaluation. Even an f-string without fields is not a
docstring. The lexer now forwards matching errors to its error handler rather
than silently dropping unterminated strings, allowing interactive input to wait
for an unfinished triple-quoted string.

The result is always the existing runtime's `unicode` type, not a newly migrated
Python 3 `str`. Direct Unicode `!r` omits the old `u` prefix and retains printable
Unicode; `!a` escapes non-ASCII code points. Empty-spec booleans display as
`True`/`False`, and inherited `object.__format__` rejects non-empty specs.
Other objects still use their existing representations and format mini-language;
this does not migrate all legacy container/long/bytes representations or add
newer format flags. Replacement expressions retain the enclosing language and
future-flag semantics, including legacy ordinary string literals and division.
Use `u'...'` or `from __future__ import unicode_literals` for non-ASCII text values.
Source-file encoding policy is unchanged: include `# -*- coding: utf-8 -*-` for
UTF-8 source files containing Chinese or other non-ASCII characters. For console
output, `PYTHONIOENCODING=utf-8` or `-Dpython.io.encoding=UTF-8` can be used.

As in pre-3.12 Python, expression backslashes and comments are rejected, inner
strings cannot reuse the outer delimiter, and format-spec replacement nesting
has a limited depth. Parenthesize lambdas inside fields. Error wording and AST
source ranges are not a promise of exact CPython compatibility.

## Build and test

From the repository root, with a JDK and Apache Ant installed:

```sh
ant jar copy-dev compile-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest
```

The classpath separator above is for Linux/macOS; use `;` on Windows. In the
current workspace, project-local Ant 1.10.15 jars are available under ignored
`build/tools`:

```sh
java -cp 'build/tools/*' org.apache.tools.ant.Main jar copy-dev compile-test
```

Those jars are not committed and are unnecessary when Ant is already installed.
A fresh checkout does not contain them. If using `-Dbuild.dir=...`, replace
`build/testclasses` in the test classpath with that directory's `testclasses`.
Java test classes must be on the classpath for `test_exceptions_jy` as well.

Run the related Python regression set with:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy
```

The new modules contain 25 function, 16 nonlocal, 33 exception-chaining, and
40 f-string test cases. Shared cases were also run on CPython 3.11; three
function tests, two exception tests and one f-string AST test are Jython-specific
and are skipped there. Twelve Java tests cover call overloads, legacy
constructors/factories, GC traversal, native display and f-string compilation.

Final f-string validation used a fresh `build/python3-fstrings-final` output
directory with Java 17 and the project's Java 8 source/target settings. The
interpreter and 138 Java test source files compiled successfully, all 12 selected
Java tests passed, and the Python regression command above reported
**All 25 tests OK**, including all 114 new Python cases. The supplied Chinese
`datetime`/`timedelta`/`time` example also ran with its f-strings unchanged,
including `strptime`, date arithmetic, timestamps and the 1.5-second sleep.
This is targeted validation, not a pass of the entire project or CPython 3 suite.

Coverage includes definition-time ordering, closures, parameter binding,
nonlocal static errors and deletion, handler cleanup, generator suspension and
exception injection, invalid causes, exception attributes, traceback handling,
cycle-safe formatting, AST construction/round trips, and interactive input.
Existing AST fixtures and closure-deletion expectations were updated for the new
behavior rather than disabling those checks.

## AST and bytecode details

The implementation changes the native ANTLR grammars, generated Java AST,
argument and scope analysis, JVM bytecode compiler, and runtime. It does not
translate Python 3 source into Python 2 source.

The AST is transitional, not the CPython 3 AST:

- `FunctionDef` adds `returns` after its original four fields.
- `arguments` keeps `args`, `vararg`, `kwarg`, and `defaults` first, followed by `posonlyargs`, `kwonlyargs`, `kw_defaults`, and `annotations`.
- Parameters remain legacy expression nodes, not `ast.arg`. Annotation entries are `keyword(name, expression)` nodes in source order.
- Positional defaults apply to the trailing parameters of `posonlyargs + args`.
- `kw_defaults` has one entry per keyword-only parameter. AST `None` means required; an expression evaluating to Python `None` is an actual default.
- `Nonlocal(names)` is a new statement node with visitor and Python subtype support.
- `Raise` keeps `type`, `inst`, and `tback`, then adds `cause`; it is not the CPython 3 `Raise(exc, cause)` layout.
- `JoinedStr(values)` and `FormattedValue(value, conversion, format_spec)` are new expression nodes with visitor, Python subtype and GC support. `conversion` is `-1` or the ordinal of `s`, `r`, or `a`; absent `format_spec` is Python `None`. Literal parts remain `Str`, not modern `Constant` nodes.
- Old four-field function and three-field raise constructors remain available. Code relying on exact `_fields` tuples must handle the additions.

Generated AST files are checked in, so normal builds do not need the old ASDL
generator. To regenerate into a staging directory with CPython 2.7:

```sh
mkdir -p build/astgen/ast build/astgen/op build/astgen/base
python2 ast/asdl_antlr.py -o build/astgen ast/Python.asdl
```

Review and copy only affected outputs into `src/org/python/antlr`. Both
`Python.asdl` and `asdl_antlr.py` must remain in sync with the affected generated
files. This legacy generator still uses Python 2 syntax. Running it directly
under Jython can fail because tuple-parameter parser methods depend on preserved
docstrings. Development used temporary CPython 3.11-compatible tooling copies
under `build`, not conversion of interpreter or library sources. The generator's
base-type constructor fix has been applied to `stmt.java` and `expr.java`; other
existing base AST files have not been broadly regenerated. New nodes also use
the corrected column-offset initialization in the generator.

Parameter slots are positional-only, positional-or-keyword, keyword-only,
optional `*args`, then optional `**kwargs`. Old Java code factories remain
available; a new overload carries the additional parameter counts.

The compiled-module API version is now **42**: stage 40 introduced function
metadata and setters; stage 41 introduced closure deletion and exception-state
helpers; stage 42 adds the f-string runtime helpers required by generated code.
This is a bytecode compatibility number, not a Python language version. Rebuild
compiled-only modules and regenerate source-backed `$py.class` caches. Do not
bypass API checks to exchange caches with an older runtime.

## Remaining migration work and boundaries

A complete migration still requires a defined Python 3 target version and
version-specific acceptance tests. Outstanding work includes:

- `yield from`, extended unpacking, `async`/`await`, asynchronous generators and comprehensions, variable annotations, assignment expressions, matrix multiplication, and Python 3.12 PEP 701 f-string extensions.
- Pattern matching, exception groups, type parameters, and newer annotation semantics where required by the eventual target version.
- Removal or isolation of Python 2-only syntax such as tuple parameters, `print`/`exec` statements, backticks, and old exception forms.
- Python 3 string/bytes, integer and division, iteration, import, class/metaclass, exception, and comprehension semantics.
- A Python 3 standard library, packaging ecosystem support, and full language/library regression coverage.
- CPython 3-compatible AST and introspection, including `inspect.signature`, and migration of alternate bytecode paths and compiler tooling.

Annotations currently use eager definition-time evaluation. There is no
`from __future__ import annotations` or deferred-evaluation implementation.
Annotation names such as `str` still refer to Python 2 builtins. Private parameter
and nonlocal names retain existing Jython name-handling conventions rather than
a comprehensive Python 3 name-mangling implementation. Error wording is not
fully aligned with CPython 3.

Exception chaining covers Python `BaseException` objects in the native JVM
compiler path. Raw Java `Throwable` objects remain raisable/catchable through
legacy interoperability, but are not accepted as Python exception-chain links;
a raw Java active exception is not attached as `__context__`. Other Python 2
exception behavior remains, including legacy exception forms and lack of
Python 3 automatic deletion of an `except ... as name` binding. The legacy
`sys.exc_clear` API and alternate `PyBytecode` interpreter have not been migrated
to a complete Python 3 exception model. The traceback override adds chaining to
the 2.7 API; it is not the entire modern Python 3 traceback API.

Accepting these constructs must not be used as a test for general Python 3
compatibility.
