# Native assignment-expression validation

## Scope and boundary

This stage adds `:=` to the existing native ANTLR/AST/ASM/JVM pipeline. The RHS
is evaluated exactly once; its PyObject is stored in the name binding and also
returned as the expression result, without Java/Python identity conversion.
It is not source translation or execution through the optional CPython backend.
The project language/version metadata remains **2.7.5b2-DEV**. Compiled-module
API advances from **47** to **48** for the new AST/compiled behavior and corrected
suspended operand-stack handling, not as a Python-version claim.

Bare assignment expressions are supported in conditions, positional arguments,
list/tuple/set displays, indices, class bases and expression decorators.
Dictionary keys/values, keyword arguments, slices, lambda bodies and ordinary
statement expression positions require the same parentheses as the covered
CPython cases. In an f-string, `(value := expression)` must be parenthesized;
`f'{value:=3}'` retains its interpretation as a format specification.

Targets are names only, in Store context; their values have Load context.
Parenthesized chaining, identity results, exceptions without rebinding,
short-circuit behavior and evaluation order are tested. Native local/global/
nonlocal bindings, closure cells, class namespace/private names, outer default
and decorator evaluation, Java classes and Java interfaces are exercised.
A walrus before a global/nonlocal declaration is rejected without broadly
changing legacy global-declaration warning rules.

**This is not full PEP 572 support.** Any assignment expression structurally
inside a list, set or dictionary comprehension or a generator expression is
rejected with `assignment expressions in comprehensions require modern
comprehension scopes`. This includes iterable/filter clauses and lambdas nested
inside comprehensions. The current Python 2 list-comprehension scope leakage
must be migrated before implementing the PEP 572 containing-scope binding and
iteration-variable restrictions. A comprehension used as the RHS of an enclosing
walrus is permitted, but retains its pre-existing scope semantics.

`ast.NamedExpr(target, value)` has Python exposure, subtype, visitor, location
and GC support. Context propagation preserves the target's Store context even
when the overall expression is a Load. Invalid/missing root targets and values
are rejected, as is ordinary assignment or deletion targeting a NamedExpr.
This is not exhaustive validation of every legacy hand-built AST. Public
`token.COLONEQUAL` is appended at **54**, preserving all previous token numbers.
`tokenize` emits `:=` as one OP token; interactive incomplete input is covered.
The indexer has a distinct serializable NNamedExpr node, local prebinding,
RHS-before-binding resolution, result type propagation and visitor support.

No comprehensions scope migration, `yield from`, async/await, standard-library
upgrade, modern constant-node schema or complete Python 3.15.2 compatibility is
claimed. Ordinary scalar operations and Python 2-only syntax remain as in the
underlying runtime. See [migration status](../PYTHON3_MIGRATION.md).

## Validation

Environment: Linux, Tencent Kona OpenJDK **17.0.20-ga**, Ant **1.10.15**, Java 8
source/target settings. An actual Java 8 JVM, Windows and macOS were not tested.
The independent shared semantic comparison used exactly **CPython 3.15.2**.

| Check | Result |
| --- | --- |
| Standard incremental build | Successful |
| Independent fresh build | Successful; 918 production and 145 Java test sources |
| New native Python tests | 45 passed, no skips |
| Exact CPython comparison | 39 shared cases passed, 6 JVM-only cases skipped |
| Selected standard Java, including indexer | 143 passed: 55 core cases and 88 indexer cases |
| Selected fresh Java, including indexer | 143 passed |
| Fresh native Python tests | 45 passed |
| Complete standard Java driver | 60 classes: 59 passed, 1 with no cases; 34,890 cases, zero failures/timeouts |
| Broad native Python regression | 51 selected: 50 passed, 1 existing test_descr skip, no failures |

Final native, CPython comparison, selected/fresh Java and complete Java runs
all succeeded. The final broad native regression exited 0. Skipped Python
coverage and the Java class with no cases are not counted as passing.

Overlapping runs are not added together. The six native-only tests cover
explicit comprehension rejection, invalid AST contexts, invalid ordinary AST
assignment/deletion targets, Java identity/subclass calls and native location/
token metadata. Shared tests exercise both new expressions and legacy nested,
method and multi-argument calls across yield. The dictionary/set grammar test
also prevents display trailing commas from being accepted in comprehensions.

Seven new Java tests establish single evaluation and Java object identity,
closure mutation through a Runnable implementation called from Java,
ThreadState calling convention on a resumed call, mixed-stack reference
traversal including PyException, AST visitor/GC edges and setter-created nodes.
The stack GC test isolates f_savedlocals in a separate frame so it cannot pass
merely because the same object also appears in Python fast locals.
Three indexer tests cover binding/reference locations, function-local scope,
serialization, parent links and generic visitor dispatch.

`test_descr` is still selected but has the existing `test_support.verify` import
skip. It is not counted as passing; neither the fixture nor skip expectations
were changed. The complete driver also discovers ConstructorSignatureTest with
no runnable cases, which is reported separately rather than counted as passed.
The earlier decorator-stage refs.foo indexer failure is historical; no assertion
was removed or weakened in this stage.

## Findings and fixes

`collect(value := object(), (yield 'ready'))` reproduced an ArrayIndexOutOfBounds
failure. The old saveStack loop incremented its index twice for stored operands;
restoreStack also failed to advance consistently across ThreadState entries,
which are reloaded rather than serialized. Each tracked operand now has one
fixed slot. Existing two-, three- and four-argument, nested and method calls
across yield pass alongside the new walrus case.

The operand spill is a mixed Java Object array, unlike the PyObject arrays used
for partially evaluated argument/decorator lists. Frame GC previously followed
only the latter. It now visits Python objects and Traverseproc values inside
both arrays while ignoring Java strings/nulls. This preserves exception edges
as well as operands. The native compiler API bump invalidates old generated
bytecode rather than relying on patched runtime traversal alone.

During implementation, two duplicate grammar-rule prefixes and a missing
NamedExpr import were corrected using build diagnostics. A new Java test used
an unsupported string-key __getitem__ overload and was corrected to the actual
__finditem__ API. These were implementation/test errors, not waived failures.

The shared AST test uses a parsed numeric literal because CPython 3.15.2 has
removed ast.Num. The JVM-only malformed-AST tests retain the native AST layout.
Native location arguments follow the existing keyword-argument constructor
convention. The previous decorator test rejecting assignment expressions is
now a positive execution-and-binding test; its await rejection remains.

ASDL, AST visitors/exposure, the template mapping and GC generator support were
updated together. The checked-in NamedExpr follows existing node conventions
and fixes column initialization for the new node. NamedExprDerived was produced
with the existing template generator in src/templates. A direct attempt to run
the legacy ASDL generator under Jython hit its known tuple-parameter/docstring
limitation; no interpreter or library sources were translated to work around it.
Normal builds use the checked-in Java classes and do not need that generator.

No unrelated indexer fixtures, global Python 2 arithmetic rules or standard
library migration were changed. Java Security Manager/logging warnings in
integration tests remain visible in the logs.

## Reproduction

From the repository root with a JDK and Ant:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_named_expressions.py -v
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_named_expressions.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.NamedExpressionTest org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
python3 tests/cpython/run_jython_regression.py --reports build/native-namedexpr/junit-final
```

The complete Java driver uses host Python only to orchestrate native JVM tests.
Its location under tests/cpython is not use of the optional CPython backend.
The driver uses the standard exploded build/exposed, build/classes and
build/testclasses layout, with a 120-second default per-class timeout.

The broad native command selects 51 modules:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_named_expressions test_python3_matmul test_operator test_tokenize test_augassign test_python3_decorator_expressions test_python3_class_bases test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration test_class test_class_jy test_classdecorators test_descr test_descr_jy test_metaclass test_java_subclasses test_subclasses_jy test_gc_jy
```

The final fresh build uses independent intermediates and distribution paths:

```sh
ant -Dbuild.dir=build/native-namedexpr/fresh-final -Ddist.dir=build/native-namedexpr/fresh-final-dist jar copy-dev compile-test jar-test
java -Dpython.home=build/native-namedexpr/fresh-final-dist -cp 'build/native-namedexpr/fresh-final/testclasses:build/native-namedexpr/fresh-final-dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.NamedExpressionTest org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
java -Dpython.home=build/native-namedexpr/fresh-final-dist -cp 'build/native-namedexpr/fresh-final/testclasses:build/native-namedexpr/fresh-final-dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_named_expressions.py -v
```

Local ignored Ant jars were invoked with
`java -cp 'build/tools/*' org.apache.tools.ant.Main` in place of installed `ant`.
They are not needed in a normal checkout with Ant installed. The exact CPython
executable is needed only for comparison. Classpath separators shown are for
Linux/macOS; use `;` on Windows. Run copy-dev after library/test edits so the
assembled dist/Lib is current; Lib alone is not a complete standard library.
jar-test provides subprocess dependencies used by Java interoperability tests.

Final logs under ignored build/native-namedexpr are build-final.log,
python-final.log, cpython-final.log, java-final.log, fresh-build.log,
fresh-java.log, fresh-python.log, full-java.log, junit-final/summary.json with
per-class logs, and regression-final.log. Intermediate build.log, python.log,
java.log and generator-failure.log are diagnostic attempts, not final acceptance
results. Commands preserve failure exit codes when redirecting output and
printing tails. Build artifacts are not part of the source change.
