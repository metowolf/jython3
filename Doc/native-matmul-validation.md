# Native matrix-operator validation

## Scope

This stage adds PEP 465's `@` and `@=` to the native ANTLR/AST/ASM/JVM path.
The compiler calls `org.python.core.MatmulSupport`; `operator.matmul`,
`operator.imatmul` and their dunder aliases use the same dispatcher. No source
translation or forwarding to the optional CPython process backend is involved.
Native version metadata remains **2.7.5b2-DEV**. Compiled-module API advances
from **46** to **47** for the new runtime entry points, not as a language-version
claim. Rebuild compiled-only modules and regenerate source-backed caches.

`@` has the precedence of multiplication and associates left-to-right. Methods
are looked up on operand classes, not in instance dictionaries, then bound as
descriptors. `__matmul__`, `__rmatmul__` and `__imatmul__` can return arbitrary
objects. `NotImplemented` triggers fallback, while ordinary exceptions propagate.
A strict right subclass with an overloaded reflected method is tried first;
same-type operands never retry `__rmatmul__`, and a prioritized reflected attempt
is not repeated. In-place fallback uses the complete binary protocol and reports
`@=` in the final unsupported-operands error.

The reflected-overload decision follows `method_is_overloaded` in the local
CPython 3.15.2 `Objects/typeobject.c`: class-level attribute binding and rich
comparison matter, not merely identity of entries in the class dictionary.
This includes inherited class methods, equivalent static-method wrappers,
descriptors and legacy unbound-method aliases. The existing Python 2 arithmetic
and coercion dispatcher is not changed. Legacy classes are supported as a native
extension without using `__coerce__`.

Names, attributes, subscripts and slices preserve target evaluation and writeback
order. Matrix left operands use typed locals across `yield`, keeping them visible
to frame GC traversal. Hand-built Store augmented targets compile through private
AugStore copies without altering the supplied AST or its parent links.

`ast.MatMult` is exposed, derivable and usable in parsed and hand-built ASTs.
Its ASDL/enum/adapter value is **13**, appended after FloorDiv so existing values
are unchanged. `token.ATEQUAL` is appended at **53**, also preserving existing
numbers. These are native compatibility choices, not CPython 3.15 token numbers
or a claim to its full AST schema. `tokenize` emits one OP token for `@=` and
retains round-trip behavior. Both full and interactive grammars are updated.
The indexer retains `@`, resolves operand references and visits the nodes, but
uses an unknown result type rather than inferring matrix-method return values.

No built-in matrix container, numerical matrix algorithm, NumPy support, Python 3
scalar arithmetic, modern string/bytes model or upgraded standard library is
provided. Built-in integers, lists and Java arrays do not automatically gain
matrix arithmetic. The AST context checks cover matrix operands and augmented
root targets, not exhaustive recursive validation of every legacy node. See
[overall migration status](../PYTHON3_MIGRATION.md) for remaining work.

## Results

Platform: Linux, Tencent Kona OpenJDK **17.0.20-ga**, Ant **1.10.15**, Java 8
source/target settings. Execution on an actual Java 8 JVM, Windows and macOS was
not verified. The shared comparison used exactly **CPython 3.15.2**.

| Check | Result |
| --- | --- |
| Standard incremental build | Successful |
| Independent fresh build | Successful; 915 production and 144 Java test sources compiled |
| New native Python module | 45 passed, no skips |
| Exact CPython comparison | 40 shared cases passed, 5 JVM-only cases skipped |
| Selected standard Java run including indexer | 133 passed: 48 core cases plus 85 indexer cases |
| Selected fresh Java run including indexer | 133 passed |
| Fresh native Python module | 45 passed |
| Fresh six-module regression | All 6 passed |
| Complete standard Java driver, repeated | 59 classes: 58 passed, 1 with no cases; 34,880 cases, no failures or timeouts |
| Broad native Python regression | 50 selected: 49 passed, 1 existing test_descr skip, no failures |

Both complete Java runs and the final broad native regression succeeded. The
class with no discovered cases is ConstructorSignatureTest; it is not counted
as a passing test class. Skipped Python coverage is not counted as passing.

Counts from overlapping runs are not additive. PythonInterpreter and
org.python.util.jython are native entry points. Host Python in the complete
Java driver only orchestrates JVM processes; its `tests/cpython` location does
not make this a CPython-backend test.

The 40 shared cases cover binary and in-place dispatch, reflected ordering,
NotImplemented, exception propagation, result identity, descriptors, type-method
updates, built-in rejection, operator arity, evaluation order, precedence,
attribute/index/slice writeback, failure without assignment, global/nonlocal
binding, generator suspension/throw/close, AST round trips and Store targets,
operator subclasses, interactive input, tokenizer round trips and decorators.
Five JVM-only cases check legacy classes, invalid/missing AST operands, stable
native numbering and Python subclasses of Java collections.

Six new Java cases establish native object identity, Java-side helper calls,
Java reflected special methods, ThreadState propagation, suspended binary and
attribute target GC traversal, legacy `+=` suspension and AST parent preservation.
Two indexer cases check operator strings, exact operand references, visitor
traversal, parent links and conservative result types.

## Findings and fixes

An initial incremental build compiled successfully but failed even on
`print(42)`, with a mismatched NEWLINE error. Adding ATEQUAL had shifted ANTLR
constants while three consumers retained old inlined numbers. `build.xml` now
invalidates PythonTokenSource, AnalyzingParser and the indexer demo Styler when
generated parser sources change. This is separate from the public token.py
numbering. Standard incremental and independent fresh builds are both checked.

Suspending an augmented attribute operation initially produced ClassFormatError
for `Lorg/python/core/PyObject;`. Saved locals need JVM internal names, not field
descriptors; the attribute-name temporary also needs String rather than PyObject.
The fix is confined to augmented-target temporary allocation. Both `@=` and
existing attribute `+=` suspension are exercised, alongside legacy augmented
assignment regression coverage. Matrix left operands separately use a typed
PyObject local rather than hiding the reference in an Object-array stack spill.

The new AST operator requires registration in CoreExposed.includes. Its integer
exposure must call the final implementation rather than a virtual wrapper, or
Python subclasses recurse through the derived dispatcher. The new node and the
ASDL Java generator now use that non-recursive exposure. Existing operator nodes
were not broadly regenerated. MatMultDerived was generated in the template
working directory and matches the existing derived-class pattern exactly.

The first broad run reported 48 modules passed, one skip and one failure:
`test_decorators` still expected `@f1 @f2` to be a syntax error. Under PEP 465 and
expression decorators this is one matrix expression. The native branch now
asserts a single MatMult decorator and TypeError for two ordinary functions;
the non-Jython Python 2 branch retains SyntaxError. The newer decorator module
also upgrades its previous matrix-rejection check to successful matrix-based
decoration. No test was deleted or skipped to accommodate the feature.

The prior stage recorded an indexer `testBasicDefsAndRefs` failure at refs.foo
offset 266 in the exploded classpath. Both complete driver runs in this stage
passed all 85 indexer cases, including that unchanged assertion. This observation
does not retroactively change the prior report. No clean historical-checkout
comparison was performed to isolate the old failure's root cause, and the
matrix feature is not claimed as its proven fix.

The existing `test_descr` skip imports removed test_support.verify/vereq helpers.
It remains selected and must not be counted as a passing module. The skip list
and fixture were not modified. Security Manager and logging-permission warnings
are retained in the regression logs.

## Reproduction

From the repository root, with a JDK and Apache Ant installed:

```sh
ant jar copy-dev compile-test jar-test
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_matmul.py -v
dist/cpython/bin/python3.15 -I -B Lib/test/test_python3_matmul.py -v
java -Dpython.home=dist -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
python3 tests/cpython/run_jython_regression.py --reports build/native-matmul/junit-final
```

The final broad native command is:

```sh
java -Dpython.home=dist -Dpython.io.encoding=UTF-8 -cp 'build/testclasses:dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_matmul test_operator test_tokenize test_augassign test_python3_decorator_expressions test_python3_class_bases test_python3_call_unpacking test_python3_mapping_unpacking test_python3_unpacking test_python3_fstrings test_python3_function_syntax test_python3_nonlocal test_python3_exception_chaining test_func_jy test_scope test_call test_extcall test_decorators test_codeop test_grammar test_ast test_ast_jy test_funcattrs test_generators test_syntax test_exceptions test_exceptions_jy test_with test_traceback test_doctest test_sys_jy test_str test_unicode test_str_jy test_unicode_jy test_dict test_dict_jy test_dictviews test_dictcomps test_set test_java_integration test_class test_class_jy test_classdecorators test_descr test_descr_jy test_metaclass test_java_subclasses test_subclasses_jy test_gc_jy
```

The fresh build uses independent intermediate and distribution directories so
it cannot overwrite the standard distribution while its regression is running:

```sh
ant -Dbuild.dir=build/native-matmul/fresh -Ddist.dir=build/native-matmul/fresh-dist jar copy-dev compile-test jar-test
java -Dpython.home=build/native-matmul/fresh-dist -cp 'build/native-matmul/fresh/testclasses:build/native-matmul/fresh-dist/jython-dev.jar:extlibs/*' org.junit.runner.JUnitCore org.python.core.MatmulTest org.python.core.DecoratorExpressionTest org.python.core.ClassBasesTest org.python.core.CallUnpackingTest org.python.core.MappingUnpackingTest org.python.core.UnpackingTest org.python.core.PyFunctionSignatureTest org.python.core.PyExceptionChainingTest org.python.core.FStringTest org.python.indexer.IndexerTest
java -Dpython.home=build/native-matmul/fresh-dist -cp 'build/native-matmul/fresh/testclasses:build/native-matmul/fresh-dist/jython-dev.jar:extlibs/*' org.python.util.jython -B Lib/test/test_python3_matmul.py -v
java -Dpython.home=build/native-matmul/fresh-dist -cp 'build/native-matmul/fresh/testclasses:build/native-matmul/fresh-dist/jython-dev.jar:extlibs/*' org.python.util.jython -B -m test.regrtest test_python3_matmul test_operator test_tokenize test_augassign test_decorators test_python3_decorator_expressions
```

In this workspace, `java -cp 'build/tools/*' org.apache.tools.ant.Main` was used
in place of installed `ant`; those local Ant jars are ignored and not required
in a fresh checkout with Ant installed. The exact CPython executable is needed
only for comparison. Java classpath separators above are for Linux/macOS; use
`;` on Windows. `jar-test` supplies Java integration subprocess dependencies.
Rerun `copy-dev` after library/test edits: `Lib` alone is not a full standard
library, whereas `dist/Lib` assembles it with lib-python/2.7.

The complete Java driver uses standard exploded classes from build/exposed,
build/classes and build/testclasses with extlibs, not the fresh JAR layout.
Its default per-class timeout is 120 seconds. Preserve each command's exit code
when redirecting output or printing log tails.

Raw logs are under ignored `build/native-matmul/`: build-final.log,
python-final.log, cpython-final.log, java-final.log, fresh-build.log,
fresh-java.log, fresh-python.log, fresh-regression.log, full-java.log,
junit-final/summary.json and per-class logs, regression-final.log and
regression-initial.log. Earlier build.log, python.log, java.log and
java-check.log are intermediate checks, not final acceptance counts.
