package org.python.core;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import junit.framework.TestCase;
import org.python.antlr.ast.arguments;
import org.python.compiler.ArgListCompiler;
import org.python.util.PythonInterpreter;

public class PyFunctionSignatureTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testJavaCallOverloads() {
        interpreter.exec("def f(*args, k=42):\n    return k\n");
        PyFunction f = (PyFunction) interpreter.get("f");
        ThreadState state = Py.getThreadState();
        PyObject arg = Py.newInteger(1);
        PyObject answer = Py.newInteger(42);
        assertEquals(answer, f.__call__());
        assertEquals(answer, f.__call__(arg));
        assertEquals(answer, f.__call__(arg, arg));
        assertEquals(answer, f.__call__(arg, arg, arg));
        assertEquals(answer, f.__call__(arg, arg, arg, arg));
        assertEquals(answer, f.__call__(state));
        assertEquals(answer, f.__call__(state, arg));
        assertEquals(answer, f.__call__(state, arg, arg));
        assertEquals(answer, f.__call__(state, arg, arg, arg));
        assertEquals(answer, f.__call__(state, arg, arg, arg, arg));
        assertEquals(answer, f.__call__(new PyObject[] {arg}));
        assertEquals(answer, f.__call__(state, new PyObject[] {arg}));
        assertEquals(answer, f.__call__(arg, Py.EmptyObjects, Py.NoKeywords));
        assertEquals(answer, f.__call__(state, arg, Py.EmptyObjects, Py.NoKeywords));
        assertEquals(Py.newInteger(9), f.__call__(state, arg,
                new PyObject[] {Py.newInteger(9)}, new String[] {"k"}));
    }

    public void testDictionariesAreTraversed() {
        interpreter.exec("def f(a: int, *, k=42) -> str:\n    return k\n");
        PyFunction f = (PyFunction) interpreter.get("f");
        final Set<PyObject> visited = Collections.newSetFromMap(
                new IdentityHashMap<PyObject, Boolean>());
        Visitproc collector = new Visitproc() {
            @Override
            public int visit(PyObject object, Object arg) {
                assertNotNull(object);
                visited.add(object);
                return 0;
            }
        };
        PyObject defaults = f.getKwDefaults();
        PyObject annotations = f.getAnnotations();
        assertEquals(0, f.traverse(collector, null));
        assertTrue(visited.contains(defaults));
        assertTrue(visited.contains(annotations));
        assertTrue(f.refersDirectlyTo(defaults));
        assertTrue(f.refersDirectlyTo(annotations));
        f.delKwDefaults();
        f.delAnnotations();
        assertFalse(f.refersDirectlyTo(defaults));
        assertFalse(f.refersDirectlyTo(annotations));
        assertFalse(f.refersDirectlyTo(null));
    }

    public void testDictionaryTraversalPropagatesResult() {
        interpreter.exec("def f(*, k=42):\n    pass\n");
        PyFunction f = (PyFunction) interpreter.get("f");
        final PyObject defaults = f.getKwDefaults();
        assertEquals(19, f.traverse(new Visitproc() {
            @Override
            public int visit(PyObject object, Object arg) {
                return object == defaults ? 19 : 0;
            }
        }, null));
    }

    public void testEmptyJavaArgumentsConstructor() throws Exception {
        arguments args = new arguments();
        ArgListCompiler compiler = new ArgListCompiler();
        compiler.visitArgs(args);
        assertTrue(compiler.names.isEmpty());
        assertTrue(compiler.getDefaults().isEmpty());
        assertEquals(0, compiler.kwonlyargcount);
        assertEquals(0, compiler.posonlyargcount);
    }

    public void testLegacyFactorySignature() {
        PyTableCode code = (PyTableCode) Py.newCode(0, new String[0], "<test>", "f", 1,
                false, false, null, 0, null, null, 0, 0);
        assertEquals(0, code.co_argcount);
        assertEquals(0, code.co_posonlyargcount);
        assertEquals(0, code.co_kwonlyargcount);
    }
}
