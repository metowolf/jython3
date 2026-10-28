# Python 3 migration status

## Status

The native JVM migration target is **Python 3.15.2**, retaining Java
interoperability. That goal is **not complete**. This working tree implements
native function-syntax, nonlocal-scope, exception-chaining, f-string,
extended iterable-unpacking, mapping-display unpacking, generalized
call-unpacking, iterable class-base, expression-decorator, matrix-operator,
assignment-expression, generator-delegation and PEP 479 generator-exception
stages on the existing Jython 2.7 runtime. It is not Jython 3, is not a Python 3 compatibility mode, and does not
make arbitrary Python 3 packages runnable.

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

## Implemented iterable unpacking

Extended assignment unpacking (PEP 3132) and the list, tuple and set iterable
display forms of PEP 448 now execute on the JVM, without the CPython backend.

```python
first, *middle, last = range(5)
assert (first, middle, last) == (0, [1, 2, 3], 4)
assert [first, *middle, last, *[5, 6]] == [0, 1, 2, 3, 4, 5, 6]
assert (*middle,) == (1, 2, 3)
assert {*middle, 2} == {1, 2, 3}
```

Each assignment sequence may contain one starred target; nested sequences may
have their own stars. Captured values are always a fresh native list, including
empty captures. Attribute/subscript targets, chain assignments, `for` and
comprehension targets, and parenthesized `with ... as` targets use the same
compiler path. Unpacking completes before stores at that sequence level;
subsequent nested assignment failures retain earlier stores, as in Python 3.

Displays allow multiple stars and consume each iterable before evaluating the
next expression. Set elements are inserted during consumption, so a hash error
stops further iteration. No global `list`, `tuple`, `set`, or `eval` lookup is
used. Registered JVM locals preserve accumulators and unpacked values across
`yield`, including suspension while evaluating an assignment receiver or index.
Java collections, Java `Iterable` objects, and Java arrays remain usable, and
Java object identity is preserved.

`Starred(value, ctx)` has native AST, visitor, subtype, source-position and GC
support. Scope analysis rejects misplaced stars, multiple stars at one target
level, missing operands, invalid star contexts and invalid nested star targets,
including manually built ASTs and unreachable branches. This is not a full
validation or migration of every legacy AST node.

Unpacking comprehensions and class-header mapping/keyword arguments are not
implemented. Dictionary `**` displays, generalized multiple `*args`/`**kwargs`
calls and iterable class bases are covered in the subsequent stages below.
The runtime's legacy iteration protocol is unchanged: Python iterator classes
still need `next`, not only `__next__`. Length-hint allocation optimizations and
their observable callbacks are not matched to CPython. Existing string/bytes behavior, container
representations and comprehension scope rules remain transitional.

## Implemented mapping displays

PEP 448 dictionary displays now accept any number of `**mapping` operands,
interleaved with ordinary key/value entries, directly in the JVM compiler.

```python
defaults = {'host': 'localhost', 'port': 8000}
overrides = {'port': 9000}
config = {**defaults, 'debug': False, **overrides}
assert config == {'host': 'localhost', 'port': 9000, 'debug': False}
assert defaults['port'] == 8000
```

The result is a fresh native `dict`; values are shallow references and later
entries override earlier equal keys. Keys need not be strings. Each mapping is
merged before evaluating the next entry group. Consecutive literal key/value
expressions are evaluated in source order before that group's dictionary is
constructed and merged. The ordinary dictionary fast path remains unchanged.
Typed JVM locals and saved expression arrays preserve both the accumulated
mapping and partially evaluated key/value pairs across `yield`.

Generic mappings use `keys()` followed by `__getitem__`, not iteration over
pairs as accepted by `dict.update`. Key iterators are exhausted before fetching
values; an exact key list remains live. Exceptions from key discovery, key
iteration, item access and insertion stop later entry evaluation. Native dict
subclasses use the dictionary fast path unless they override `__iter__`, in
which case their mapping protocol is used. Java `Map` implementations and
native namespace mappings remain supported without CPython.

The existing `Dict(keys, values)` AST uses a `None` key slot for each `**` value,
distinct from an expression evaluating to a Python `None` key. No new AST node
or field is needed. Scope analysis validates equal list lengths, non-null
values and expression contexts, including hand-built ASTs. Dictionary displays
cannot be assignment/deletion targets, including in nested targets, loops,
comprehensions, context managers and unreachable branches. Using a dictionary
as the receiver of a subscript target remains valid.

This stage does not migrate the dictionary object model: insertion order is
**not guaranteed**, views remain based on the existing runtime, and hash/equality
callback counts, hash reuse, large-literal allocation strategies and concurrent
mutation behavior are not matched to CPython. Mapping key iterators retain the
legacy iteration/length-hint boundaries stated above. Error wording is not an
exact compatibility promise. Class-header mapping/keyword arguments and unpacking
comprehensions remain outstanding; calls and iterable class bases are covered below.

The mapping module adds 42 cases: 34 shared cases also pass on CPython 3.15.2,
and 8 are JVM-specific. All 42 native cases and 24 selected Java cases (including
6 new mapping cases) passed. The broader native Python regression reported
**All 33 tests OK**, including dictionary, set and Java integration modules.
The complete Java driver reported 34,848 cases with the one previously recorded
indexer failure and no timeouts. See
[the mapping validation report](Doc/native-mapping-validation.md) for commands,
test-JAR prerequisites, and detailed results. These are not claims of full
Python 3.15.2 compatibility.

## Implemented call unpacking

Generalized PEP 448 function calls execute directly on the JVM:

```python
def collect(*args, **kwargs):
    return args, kwargs

assert collect(0, *[1], 2, *[3], x=4, **{'y': 5}, z=6, **{'w': 7}) == (
    (0, 1, 2, 3), {'x': 4, 'y': 5, 'z': 6, 'w': 7})
```

Multiple iterable and mapping operands may be interleaved with ordinary values
in their respective argument groups. An ordinary positional value cannot follow a
keyword argument, and iterable expansion cannot follow mapping expansion.
Explicit keywords may follow a mapping expansion. Repeated explicit names are
compile-time errors, including in unreachable hand-built ASTs. Runtime keyword
collisions raise `TypeError`, unlike dictionary displays' last-value-wins rule.
Final keyword names must be strings in the current native object model.

The callable is evaluated first, then all positional expressions, including
stars written after named arguments, then keyword expressions. Multiple-star
calls consume each iterable before the next positional expression. If the only
positional argument is a single star, its operand is evaluated early but consumed
after keyword evaluation/merging, as observed on CPython 3.15.2. Consecutive named
values are all evaluated before that group's collision checks. Mapping merges
check duplicate and unhashable keys before fetching the corresponding value;
non-string key rejection happens after all merges. User iterator exceptions
propagate without replacing an internal `TypeError` with an argument error.

Custom mappings use `keys()` and item lookup. Non-exact-list key iterables are
consumed before fetching values; an exact list stays live. Native dictionary
subclasses use the fast path unless they override `__iter__`. The accumulator
uses the existing `PyObject.__call__(ThreadState, PyObject[], String[])` ABI;
Java iterables, arrays, maps, overloaded methods and constructors remain usable.
Typed JVM locals and GC traversal preserve intermediate state across `yield`,
including nested calls and partially evaluated keyword groups. Ordinary calls
without expansion keep their existing fast paths.

The parser puts `Starred` entries in `Call.args` and `keyword(arg=None, value=...)`
in `Call.keywords`. The legacy `Call.starargs` and `Call.kwargs` fields and Java
constructors are retained. Pure legacy manually built calls still compile through
the old path; mixing legacy fields with modern expansion entries is rejected.
`Python.asdl` documents nullable keyword names without changing the Java layout.

This does not implement ordered final `**kwargs` dictionaries (PEP 468), modern
`str`/`bytes` separation, the modern iteration protocol, or exact CPython callback
counts, length hints, hash caching, error messages and concurrent-mutation behavior.
The AST remains transitional. The indexer's call conversion now preserves star
operand references without a class-cast failure, but does not implement complete
expansion-arity inference or migrate the entire alternate indexer AST.

All 49 new native Python cases passed; 42 shared cases also passed on CPython
3.15.2, with 7 JVM-specific cases skipped there. The final fresh build compiled
912 production and 141 Java test sources. All 30 selected Java cases passed on
standard and fresh builds, and the native regression reported **All 35 tests OK**.
The complete Java driver reported 34,856 cases with one previously recorded
indexer reference failure and no timeouts; the new standard-library indexing
regression was fixed, with two added reference tests. See
[call validation](Doc/native-call-validation.md) for commands, detailed results
and the unresolved failure. These results do not establish full Python 3.15.2
compatibility.

## Implemented iterable class bases

Class definitions accept any number of `*iterable` bases mixed with ordinary
base expressions, including a trailing comma:

```python
class Left(object):
    pass
class Right(object):
    pass
class Combined(*[Left], *[], Right):
    pass
assert Combined.__bases__ == (Left, Right)
```

Each operand is evaluated once in the surrounding scope. Stars are consumed
before the next base expression and before running the class body. The expanded
sequence is passed to the existing native class factory: ordinary Python
inheritance, inherited metaclasses, and Java classes/interfaces retain their
runtime behavior. Sources are not mutated; duplicate bases and inconsistent
MROs are rejected by the existing type machinery. A parenthesized tuple is now
correctly one base expression, not implicitly flattened: `class C((A, B))`
fails at runtime, while `class C(*(A, B))` expands both bases.

Class decorator expressions now evaluate top-to-bottom before any bases or the
body, for both starred and ordinary class definitions. They are applied
bottom-to-top after class construction. Failures in iteration or decorator
creation stop subsequent base/body evaluation; failed construction or decorator
application does not replace an existing class-name binding. These ordering
changes replace the legacy compiler's post-body decorator-expression evaluation.

`ClassDef` retains its four fields and Java constructors; `bases` contains
`Starred(value, Load)` entries. Scope analysis validates base contexts and
operands even in unreachable ASTs, while the partial parser recognizes incomplete
starred class headers. The indexer preserves base-operand references without
claiming complete dynamic-base or MRO inference.

The compiler reuses the native list-expansion helper and saves intermediate
bases and decorators in typed locals across `yield`, including nested expression
suspension, `throw()` and `close()`. Frame GC traversal now includes `PyObject[]`
elements in saved locals, including partially evaluated decorator/base/argument
arrays; it skips empty slots and preserves visitor early-return behavior.

This stage is not the full Python 3 class-creation protocol. `metaclass=` and
other class-header keywords, `**mapping` in class headers, `__prepare__`,
`__mro_entries__`/`__orig_bases__`, `__classcell__`/zero-argument `super`, and
modern class hooks remain migration work. Empty base expansion still creates
the same legacy class kind as a class with no explicit bases, not an implicit
Python 3 `object` subclass. Legacy iteration, length-hint callback, error-text
and object-model limitations remain.

All 44 new native Python cases passed. On CPython 3.15.2, 37 shared cases passed
and 7 JVM-only cases were skipped. Standard and fresh builds passed all 37
selected Java cases; the fresh build compiled 912 production and 142 Java test
sources. The expanded native regression selected 45 modules: 44 passed and
`test_descr` was skipped for its existing missing test-helper imports, with no
failures. The complete Java driver reported 34,864 cases with one previously
recorded indexer reference failure and no timeouts. See
[class-base validation](Doc/native-class-bases-validation.md) for commands,
fixes, skipped coverage and the unresolved failure. This is not complete native
Python 3.15.2 compatibility.

## Implemented expression decorators

Following PEP 614's relaxed decorator syntax, `@` accepts one expression from
the current native language rather than only a dotted name with one optional
call. Functions and classes use the same rule:

```python
def keep(value):
    return value

decorators = [keep]
@decorators[0]
def answer():
    return 42

@keep if True else missing
class Example(object):
    pass
```

Parenthesized expressions, subscripts and slices, chained calls and attributes,
lambdas (also unparenthesized), conditionals, boolean/binary expressions,
comprehensions, and the already-supported iterable/mapping displays and calls
can produce a decorator. A comma-separated tuple must be parenthesized; a bare
star is not a decorator. Non-callable expression results fail at application
time, not during parsing. Existing simple and dotted decorators still work.

Decorator expressions evaluate once, top-to-bottom, in the enclosing scope,
before function defaults or class bases/body. Application is bottom-to-top;
failures retain an existing definition-name binding. This reuses the existing
native compiler and `PyObject.__call__` path, including Java methods, Java
collection lookup, object identity and decorated Java subclasses/interfaces.
Parenthesized `yield` expressions can suspend an enclosing generator during
decorator evaluation. Typed locals and frame array traversal retain partially
evaluated decorators across subsequent decorators, defaults and class bases.

The AST retains the existing `decorator_list` of expression nodes and definition
fields. Scope analysis now rejects null decorators and non-Load root contexts,
as well as misplaced bare stars, even in unreachable definitions; this is not a
complete recursive validator for every legacy expression node. Interactive input
uses the same relaxed rule. The indexer retains class decorator lists, resolves
them in the enclosing scope, and visits both function and class decorators.
Class index AST serialization is versioned to reject old caches that omit those
lists; the existing cache loader reparses source. Decorator replacement/type
inference and complete modern-expression support in the indexer are not claimed.

The decorator stage did not implement matrix multiplication or assignment
expressions; later stages below add them, including inside decorators.
Generator delegation is implemented in its own later stage below.
`async`/`await`, modern comprehension scopes, deferred annotations
and the full Python 3 object model remain outstanding, including inside
decorators. This is not full PEP 614 support for every modern expression.
The decorator stage needed no runtime ABI or native AST layout change and kept
compiled-module API **46**; the matrix stage below advances it to **47**.

All 39 new native Python cases passed. On CPython 3.15.2, 33 shared cases passed
and 6 JVM-specific cases were skipped. Standard and fresh builds passed all 42
selected Java cases. The broad native regression selected 46 modules: 45 passed
and `test_descr` retained its existing skip, with no failures. The complete Java
driver reported 34,872 cases with one previously recorded indexer reference
failure and no timeouts; it is not all green. A separate fresh JAR-based run
passed 125 cases including the indexer, but does not establish that failure as
fixed. See [decorator validation](Doc/native-decorators-validation.md) for
commands, classpath differences and remaining boundaries.

## Implemented matrix operators

PEP 465's `@` and `@=` now compile directly to JVM calls to `MatmulSupport`.
They do not translate source or forward execution to the optional CPython backend.
`@` has multiplication-level precedence and is left-associative:

```python
class Matrix(object):
    def __init__(self, label):
        self.label = label

    def __matmul__(self, other):
        return Matrix((self.label, other.label))

value = Matrix('a') @ Matrix('b')
value @= Matrix('c')
assert value.label == (('a', 'b'), 'c')
```

Special methods are looked up on operand classes and bound as descriptors.
`__matmul__`, `__rmatmul__` and `__imatmul__` support `NotImplemented` fallback,
right-subclass reflected priority and arbitrary replacement results. Same-type
operands do not retry the reflected method; a prioritized reflected attempt is
not repeated. Class-level descriptor binding and comparison determine reflected
priority, including static/class methods and legacy unbound-method aliases.
Exceptions propagate without fallback. `@=` falls back to the full binary
protocol if the in-place method is absent or returns `NotImplemented`.

Targets are evaluated once and assigned only after successful dispatch. Names,
attributes, subscripts, slices, closures and generator suspension use native
compiler machinery. Typed operand/target locals remain visible to frame GC
traversal. Augmented attribute temporaries now record the attribute name as a
Java String and object locals as JVM internal names, fixing invalid suspended
frame bytecode; legacy `+=` suspension is also exercised.

`ast.MatMult`, AST compilation and subclassing, interactive parsing, `tokenize`,
and `operator.matmul`/`operator.imatmul` plus their dunder aliases are included.
Hand-built Store targets compile through private AugStore copies without
mutating the supplied AST. Scope checks reject missing operands, invalid root
contexts and invalid augmented targets, but do not recursively modernize all
legacy AST validation. The indexer preserves both operand references and `@`,
and uses an unknown result type instead of scalar-promotion heuristics.

ASDL/enum/adapter value **13** is appended without renumbering old operators.
`token.ATEQUAL` is appended at **53** while old token numbers remain unchanged;
this is not CPython 3.15's token numbering or its complete AST layout. The new
operator's integer exposure avoids recursive derived-class dispatch; the AST
source generator is updated but old operators are not broadly regenerated.
ANTLR regeneration now invalidates the three classes that inline lexer/parser
token constants, so incremental builds do not silently retain old numbers.

All **45** new native Python cases passed. The exact CPython 3.15.2 comparison
passed **40** shared cases and skipped **5** native-only cases. Standard and
independent fresh JAR-based Java runs passed **133** cases, including six new
native interoperability, ThreadState, AST and GC tests and two new indexer cases.
The fresh native run passed all 45 cases and its six-module regression passed.
The final broad native regression selected **50** modules: **49 passed**, with
only the existing `test_descr` skip. Two complete Java driver runs reported
**34,880** cases, no failures or timeouts; 58 of 59 classes passed and one had no
cases. The prior indexer failure did not recur, but its historical root cause
has not been isolated. See [matrix validation](Doc/native-matmul-validation.md)
for commands, implementation fixes and boundaries. Earlier stage counts above
remain historical results, not substitutes for this stage's regression.

There is no built-in matrix container or numerical matrix algorithm. Integers,
lists and Java arrays do not acquire matrix arithmetic automatically. NumPy,
Python 3 scalar arithmetic and the complete Python 3.15.2 runtime/library remain
out of scope. This stage used compiled-module API **47**; assignment
expressions below advance it to **48**, not a language-version claim.

## Implemented assignment expressions

The native parser and JVM compiler now support `:=` outside comprehensions:

```python
values = iter([1, 2, 0])
seen = []
while current := next(values):
    seen.append(current)
assert seen == [1, 2]
assert current == 0

marker = object()
assert (saved := marker) is marker
assert saved is marker
```

The right-hand expression is evaluated once, then its object is bound and
returned without conversion. Exceptions leave the old binding unchanged.
Precedence, short-circuiting and required parentheses follow the covered
CPython 3.15.2 cases. Bare assignment expressions work in `if`/`elif`/`while`,
positional calls, list/tuple/set displays, simple indices, class bases and
expression decorators. Other positions, including dictionary keys/values,
keyword arguments, slices, lambda bodies and f-string fields, require parentheses.
In `f'{value:=3}'`, the colon still starts a format specification, not a binding.

Only names are accepted as targets. Ordinary assignment/deletion of a
NamedExpr, chained unparenthesized walruses, constants and `__debug__` targets
are rejected. Native locals, closure cells, `global`, `nonlocal`, class namespace
binding and private-name mangling are retained. Defaults, decorators and bases
bind in their existing enclosing evaluation scope. A walrus before a global or
nonlocal declaration is rejected; unrelated legacy global-warning behavior has
not been rewritten. Calls and assignments preserve Java/Python object identity.

**Comprehension limitation:** assignment expressions anywhere inside list, set,
dictionary comprehensions or generator expressions are deliberately rejected
with `assignment expressions in comprehensions require modern comprehension
scopes`. This conservative boundary includes inner lambdas and iterable/filter
clauses. Existing Python 2 list-comprehension leakage must be migrated before
PEP 572 outer binding and rebinding restrictions can be implemented correctly.
A comprehension may be the RHS of an enclosing assignment expression, such as
`(values := [n * 2 for n in source])`; its old scope behavior remains unchanged.
This is a bounded syntax/runtime stage, **not full PEP 572 support**.

`ast.NamedExpr(target, value)` has visitor, Python subclass and GC support.
The target is a Name in Store context and the value is in Load context. Grammar
context propagation preserves these separate roles. Hand-built nodes compile
without AST mutation; missing/invalid root targets and values are rejected.
These checks do not constitute exhaustive recursive modern AST validation.
`token.COLONEQUAL` is appended at **54** without renumbering existing public
constants, and tokenizer round trips and incomplete interactive input are tested.
The indexer adds a distinct serializable node, prebinds local target names,
resolves the RHS before assignment and carries its type into the result.

Generator coverage exposed an existing mixed operand-stack spill bug: save and
restore advanced indices inconsistently, especially around unsaved ThreadState
slots. The compiler now assigns one fixed array slot per tracked operand and
reloads ThreadState on resume. Frame traversal follows Python references inside
mixed Object arrays, including exception objects, while ignoring Java strings
and empty slots. Existing multi-argument and nested calls across `yield` are
also covered, not only newly introduced syntax.

All **45** new native Python cases passed. Exact CPython 3.15.2 passed **39**
shared cases and skipped **6** native-specific cases. Standard and independent
fresh Java runs passed **143** cases, including seven new identity, interface,
ThreadState, AST and GC tests and three new indexer cases. The fresh native run
passed all 45 cases. The final broad native regression selected **51** modules:
**50 passed**, with only the existing `test_descr` skip. The complete Java driver
reported **34,890** cases, no failures or timeouts; 59 of 60 classes passed and
one had no runnable cases. All 88 indexer cases passed. See
[assignment-expression validation](Doc/native-namedexpr-validation.md) for
commands, fixes and boundaries. This stage used compiled-module API **48** for
the new syntax/AST and corrected suspended-stack behavior; the next stage uses
**49**. Standard-library upgrading,
complete Python 3 scopes and the optional CPython backend remain separate work.

## Implemented generator delegation

The native JVM compiler supports `yield from iterable` and generator return
values, without source translation or forwarding execution to CPython:

```python
def inner():
    received = yield "ready"
    return received

def outer():
    result = yield from inner()
    yield result

generator = outer()
assert next(generator) == "ready"
assert generator.send(42) == 42
```

The operand and its iterator are evaluated once. Delegation forwards next,
non-None sends, exception arguments/traceback and close calls. StopIteration
from an invoked iterator method completes the expression with its internal
`value`. Following CPython 3.15's CLEANUP_THROW behavior, an injected
StopIteration with no delegate throw method, or one raised by a delegate close
call, also completes delegation. Ordinary failures remain catchable by the outer
generator. GeneratorExit calls the delegate's close rather than its throw.
Failed throw attribute lookup leaves the delegator suspended; failed close
attribute lookup is reported as unraisable and closing continues. Reentrant
send/throw/close is rejected before modifying the paused frame's input.

`return value` now terminates a native generator with StopIteration.value;
returning a tuple preserves it as one object, not several exception arguments.
The StopIteration value is stored independently of args and the instance dict,
is GC-visible, and is not replaced by a subclass's Python property when fetching
a delegation result. A generator that catches GeneratorExit and returns a value
returns it from close, matching the covered CPython 3.15.2 behavior. A delegate's
close return is ignored. Generators expose read-only `gi_yieldfrom` and a
`__next__` alias in addition to the legacy `next` method.

The compiler uses a native state helper in a typed saved local, preserving
pending expressions and augmented-assignment targets across suspension. A
pending generator return also uses a typed local, so a suspending finally block
cannot lose its return value or GC reference. Completion clears delegation and
saved-frame references. Java tests isolate these edges from ordinary locals.
`ast.YieldFrom(value)` has visitor, subtype, location and GC support. The indexer
retains the operand references and parent links, but conservatively assigns an
unknown result type instead of claiming generator-return inference.

**Boundaries:** This delegation stage initially retained legacy escaped
StopIteration behavior; the subsequent PEP 479 stage below supersedes that
boundary. Yield-from anywhere inside a comprehension is conservatively rejected with a modern-comprehension-scopes
message, including first iterable clauses and nested lambdas that CPython may
allow. This avoids silently inheriting Python 2 scope behavior. General iterator
migration from next to __next__, coroutine/async-generator support, recursive
modern AST validation, and alternate legacy bytecode execution are not covered.
The new delegation path understands __next__, legacy next and Java iterators;
this does not modernize every iterator entry point in the runtime.

At completion of the delegation stage, its Python suite had **51** cases:
all passed natively; exact CPython 3.15.2
passes **45** shared cases and skips **6** JVM-specific cases. The selected Java
suite passes **152** cases, including seven new runtime/AST/GC cases and two new
indexer cases. An independent fresh build compiled **922** production and **146**
Java test sources; its selected Java and native Python runs also passed **152**
and **51** cases, respectively. The complete Java driver reported **34,899**
passing cases, with **60** of **61** classes passing and one reporting no cases;
there were no failures or timeouts. The **53**-module native regression passed
**52** modules and retained the existing `test_descr` import skip. Overlapping
runs are not summed, and skipped/no-case entries are not counted as passes.
Details and commands are in the
[yield-from validation report](Doc/native-yieldfrom-validation.md).
Compiled-module API is now **49** for new yield-from helpers and generator
return/paused-frame behavior. The project language version is still 2.7.5b2-DEV.

## Implemented generator exception conversion

PEP 479 is now unconditional in the native JVM generator path. A StopIteration
or subclass escaping an executing generator becomes
`RuntimeError("generator raised StopIteration")`. The original exception instance
is preserved as both `__cause__` and `__context__`, with its traceback and value
intact, and `__suppress_context__` is true. No exception reconstruction or
stringification of the original instance is required. Java callers of
`PyGenerator.__iternext__` receive the error rather than a false exhaustion signal.

```python
def broken():
    yield 1
    raise StopIteration(42)

generator = broken()
assert next(generator) == 1
try:
    next(generator)
except RuntimeError as error:
    assert error.__cause__.value == 42
    assert error.__context__ is error.__cause__
```

Conversion happens only after body handlers and finally blocks unwind. A
StopIteration caught inside the generator, normal `return value`, exhaustion of
an iterator, and termination consumed by `yield from` are not errors. Throwing
StopIteration into a suspended plain generator converts it if uncaught; throwing
it into an unstarted or already closed generator does not execute its body and
retains StopIteration, as observed on exact CPython 3.15.2. Close cleanup that
raises StopIteration is an error, while a return from a caught GeneratorExit
still delivers its value. Nested delegation does not repeatedly wrap errors.
Generator-expression bodies use the same rule; this does not modernize their
scope semantics or relax the existing comprehension syntax boundaries.

`from __future__ import generator_stop` is accepted as a no-op, including the
usual future-placement checks. The historical explicit compile flag `0x800000`
is accepted, retained in code objects and inherited by dynamic compile unless
`dont_inherit` is requested. Like CPython 3.15.2, the no-op import itself does not
set that bit. PEP 479 cannot be disabled by omitting the flag.

The bundled `contextlib` preserves the original StopIteration raised by a with
body instead of leaking its PEP 479 wrapper; actual setup/cleanup errors still
propagate. The nested generators in `difflib._mdiff` now use return or explicit
exhaustion handling rather than relying on escaped StopIteration. These are
focused changes to the retained 2.7 library, not a modern standard-library port.
Legacy generator doctests and the prior yield-from suite now check the new
behavior without removing the iterator-completion assertions.

Validation: **45** native Python cases passed; exact CPython 3.15.2 passed **43**
shared cases and skipped **2** JVM-only cases. The deduplicated selected Java
suite passed **158** cases: **68** core cases (including six new tests) and
**90** indexer cases. An independent fresh build compiled **922** production
and **147** Java test sources and passed the same **158** Java and **45** Python
cases. The complete Java driver reported **34,905** passing cases, no failures
or timeouts, with **61** of **62** classes passing and one with no cases. The
**61**-module native regression passed **60** modules and retained the existing
`test_descr` import skip; overlapping runs are not summed. Details and commands
are in [the PEP 479 validation report](Doc/native-generator-stop-validation.md).
The project version remains **2.7.5b2-DEV** and compiled-module API remains
**49**: this stage changes generator runtime semantics, not the generated call
ABI. Rebuild the runtime and run copy-dev for the updated library; old cached
native generator bodies also execute through the new exception boundary.
No async/coroutine semantics, full tracing-event parity, complete modern AST
validation, or alternate bytecode-interpreter migration is claimed.

## Build and test

From the repository root, with a JDK and Apache Ant installed:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.core.UnpackingTest org.python.core.MappingUnpackingTest org.python.core.CallUnpackingTest org.python.core.ClassBasesTest org.python.core.DecoratorExpressionTest org.python.core.MatmulTest org.python.core.NamedExpressionTest org.python.core.YieldFromTest org.python.core.GeneratorStopTest
```

The classpath separator above is for Linux/macOS; use `;` on Windows. In the
current workspace, project-local Ant 1.10.15 jars are available under ignored
`build/tools`:

```sh
java -cp 'build/tools/*' org.apache.tools.ant.Main jar copy-dev compile-test jar-test
```

Those Ant jars are not committed and are unnecessary when Ant is already installed.
A fresh checkout does not contain them. The `jar-test` target supplies the separate
`dist/jython-test.jar` needed by Java integration subprocesses.
If using `-Dbuild.dir=...`, replace
`build/testclasses` in the test classpath with that directory's `testclasses`.
Java test classes must be on the classpath for `test_exceptions_jy` as well.

Run the related Python regression set with:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_generator_stop test_python3_yield_from test_python3_named_expressions test_python3_matmul test_operator test_tokenize test_augassign test_python3_decorator_expressions test_python3_class_bases test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_generators_jy test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration test_class test_class_jy test_classdecorators test_descr test_descr_jy test_metaclass test_java_subclasses test_subclasses_jy test_gc_jy test_genexps test_contextlib test_difflib test___future__ test_future test_iter test_itertools
```

This selects 61 modules, retaining the preceding 53-module delegation set
and adding the PEP 479 suite plus generator-expression, contextlib, difflib,
future-metadata, future-statement, iterator and itertools coverage.
The legacy `test_descr` module is currently skipped because it imports removed
`test.test_support.verify`/`vereq` helpers; it is already listed in the existing
Jython skip expectations. It must not be counted as a passing module. Run
`copy-dev` after editing library tests so this command sees the current sources
in the assembled `dist/Lib`, which combines `lib-python/2.7` with `Lib` overrides.

The earlier modules contain 25 function, 16 nonlocal, 33 exception-chaining, and
40 f-string test cases. Shared cases were also run on CPython 3.11; three
function tests, two exception tests and one f-string AST test are Jython-specific
and are skipped there. Twelve Java tests cover call overloads, legacy
constructors/factories, GC traversal, native display and f-string compilation.

Final f-string validation used a fresh `build/python3-fstrings-final` output
directory with Java 17 and the project's Java 8 source/target settings. The
interpreter and 138 Java test source files compiled successfully, all 12 selected
Java tests passed, and the then-current 25-module Python regression set reported
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

The subsequent unpacking stage adds 42 Python cases (35 shared and 7 JVM-only)
and 6 Java cases. A fresh Java 17 build in `build/native-unpacking/fresh` compiled
911 interpreter sources and 139 Java test sources. All 42 unpacking cases and
all 18 selected Java cases passed; the then-current regression command reported
**All 26 tests OK**. The 35 shared cases also passed on CPython 3.15.2, with the
7 JVM-specific cases skipped. The combination test covers 144 different
before/after/input-length configurations within one case. These results are not
a claim of full Python 3.15.2 compatibility. See
[the native validation report](Doc/native-jvm-validation.md) for full Java
regression results, reproduction commands and remaining boundaries.

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
- `NamedExpr(target, value)` binds a Store-context Name and produces its Load-context value; it includes visitor, Python subtype and GC support.
- `YieldFrom(value)` delegates to an iterator; it includes visitor, Python subtype and GC support.
- `Raise` keeps `type`, `inst`, and `tback`, then adds `cause`; it is not the CPython 3 `Raise(exc, cause)` layout.
- `JoinedStr(values)` and `FormattedValue(value, conversion, format_spec)` are new expression nodes with visitor, Python subtype and GC support. `conversion` is `-1` or the ordinal of `s`, `r`, or `a`; absent `format_spec` is Python `None`. Literal parts remain `Str`, not modern `Constant` nodes.
- `Starred(value, ctx)` represents extended assignment, iterable display, call and class-base unpacking. It has visitor, Python subtype and GC support.
- `Call.args` now contains stars and `Call.keywords` contains null-name mapping entries. Legacy `starargs`/`kwargs` fields and constructors remain available for pure legacy calls, but cannot be mixed with modern expansion entries.
- `ClassDef.bases` now contains stars but keeps its original four-field layout; class keywords are not yet supported.
- `Dict(keys, values)` now uses a null key slot for each mapping display expansion; ordinary `None` keys remain expression nodes. List lengths must match and values cannot be null.
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

The compiled-module API version is now **49**: stage 40 introduced function
metadata and setters; stage 41 introduced closure deletion and exception-state
helpers; stage 42 added f-string runtime helpers; stage 43 added iterable
unpacking helpers; stage 44 added mapping-display merging helpers; stage 45
added the generalized call accumulator and invocation helpers; stage 46
invalidates caches for the new class-base parsing and decorator evaluation order;
stage 47 adds the native matrix-dispatch entry points; stage 48 adds assignment
expressions and corrects suspended operand-stack handling; stage 49 adds
yield-from helpers and generator-return/paused-frame behavior. The subsequent
PEP 479 runtime stage retains API 49; it adds no generated-call ABI dependency.
This is a bytecode/cache compatibility number, not a Python language version.
Rebuild compiled-only modules and regenerate source-backed `$py.class` caches.
Do not bypass API checks to exchange caches with an older runtime.

## Remaining migration work and boundaries

The target is Python 3.15.2 for both language and standard-library behavior;
the native path must meet it without forwarding execution to CPython. Full
version-specific acceptance tests remain to be established. Outstanding work
includes:

- Yield-from inside comprehensions, class-header keywords and mapping expansion, unpacking comprehensions, `async`/`await`, asynchronous generators and comprehensions, variable annotations, assignment expressions inside comprehensions, and Python 3.12 PEP 701 f-string extensions.
- Pattern matching, exception groups, type parameters, deferred annotation semantics, and the other language/library changes through Python 3.15.2.
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
