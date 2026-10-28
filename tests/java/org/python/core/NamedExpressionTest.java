package org.python.core;

import junit.framework.TestCase;
import org.python.antlr.Visitor;
import org.python.antlr.ast.Name;
import org.python.antlr.ast.NamedExpr;
import org.python.antlr.ast.expr_contextType;
import org.python.util.PythonInterpreter;

/** Native assignment expressions and suspended stack ownership. */
public class NamedExpressionTest extends TestCase {
    private PythonInterpreter interpreter;

    public static class Bridge {
        public final PyObject marker = Py.java2py(new Object());
        public int calls;
        public PyObject value() {
            calls++;
            return marker;
        }
    }

    @Override
    protected void setUp() { interpreter = new PythonInterpreter(); }
    @Override
    protected void tearDown() { interpreter.close(); }

    public void testNativeJavaIdentityAndSingleEvaluation() {
        Bridge bridge = new Bridge();
        interpreter.set("bridge", bridge);
        interpreter.exec("result = (bound := bridge.value())\n");
        assertEquals(1, bridge.calls);
        assertSame(bridge.marker, interpreter.get("result"));
        assertSame(bridge.marker, interpreter.get("bound"));
    }

    public void testNativeClosureAndJavaInterface() {
        interpreter.exec("from java.lang import Runnable\n"
                + "def outer():\n value = 0\n class Task(Runnable):\n"
                + "  def run(self):\n   nonlocal value\n   (value := value + 1)\n"
                + " return Task(), lambda: value\n"
                + "task, read = outer()\n");
        Runnable task = (Runnable)interpreter.get("task").__tojava__(Runnable.class);
        task.run();
        task.run();
        assertEquals(2, interpreter.get("read").__call__().asInt());
    }

    public void testThreadStateOnResumedCall() {
        PyObject marker = Py.java2py(new Object());
        PyObject callback = new PyObject() {
            @Override
            public PyObject __call__(ThreadState state, PyObject first, PyObject second) {
                assertSame(Py.getThreadState(), state);
                assertSame(marker, first);
                assertEquals(42, second.asInt());
                return first;
            }
        };
        interpreter.set("marker", marker);
        interpreter.set("callback", callback);
        interpreter.exec("def gen():\n yield callback(value := marker, (yield 'ready'))\n"
                + "iterator = gen()\nnext(iterator)\n");
        PyGenerator generator = (PyGenerator)interpreter.get("iterator");
        assertSame(marker, generator.send(Py.newInteger(42)));
        generator.close();
    }

    public void testSuspendedMixedStackTraversal() {
        interpreter.exec("def collect(*args): return args\ndef gen():\n"
                + " yield collect(value := object(), (yield 'ready'))\n"
                + "iterator = gen()\nnext(iterator)\n");
        PyFrame frame = ((PyGenerator)interpreter.get("iterator")).gi_frame;
        PyObject marker = frame.getLocals().__finditem__("value");
        assertNotNull(marker);
        boolean saved = false;
        for (Object local : frame.f_savedlocals) {
            if (local instanceof Object[] && !(local instanceof PyObject[])) {
                for (Object element : (Object[])local) {
                    assertFalse(element instanceof ThreadState);
                    if (element == marker) saved = true;
                }
            }
        }
        assertTrue(saved);
        // Isolate the spill edge, rather than succeeding because of fast locals.
        PyFrame isolated = new PyFrame(null, null, null, null);
        isolated.f_savedlocals = frame.f_savedlocals;
        assertTrue(isolated.refersDirectlyTo(marker));
        assertEquals(31, isolated.traverse((value, arg) -> value == marker ? 31 : 0, null));
        interpreter.exec("iterator.close()\n");
    }

    public void testMixedStackExceptionTraversal() {
        PyObject marker = Py.java2py(new Object());
        PyException exception = new PyException(Py.ValueError, marker);
        PyFrame frame = new PyFrame(null, null, null, null);
        frame.f_savedlocals = new Object[] {new Object[] {"attribute", exception, null}};
        assertTrue(frame.refersDirectlyTo(marker));
        assertFalse(frame.refersDirectlyTo(null));
        assertEquals(37, frame.traverse((value, arg) -> value == marker ? 37 : 0, null));
    }

    public void testAstVisitorAndGc() throws Exception {
        interpreter.exec("import ast\nnode = ast.parse('(target := source)', mode='eval').body\n");
        NamedExpr node = (NamedExpr)interpreter.get("node");
        assertEquals(expr_contextType.Store, ((Name)node.getInternalTarget()).getInternalCtx());
        assertEquals(expr_contextType.Load, ((Name)node.getInternalValue()).getInternalCtx());
        final java.util.List<String> names = new java.util.ArrayList<String>();
        node.accept(new Visitor() {
            @Override
            public Object visitName(Name name) {
                names.add(name.getInternalId());
                return null;
            }
        });
        assertEquals(java.util.Arrays.asList("target", "source"), names);
        PyObject dictionary = node.fastGetDict();
        for (PyObject reference : new PyObject[] {node.getInternalTarget(), node.getInternalValue(), dictionary}) {
            assertTrue(node.refersDirectlyTo(reference));
            assertEquals(41, node.traverse((value, arg) -> value == reference ? 41 : 0, null));
        }
    }

    public void testAstSetterEdgesAndLocations() {
        interpreter.exec("import ast\nnode = ast.NamedExpr()\n"
                + "node.target = ast.Name(id='target', ctx=ast.Store())\n"
                + "node.value = ast.Num(n=42)\nnode.lineno = 7\nnode.col_offset = 3\n"
                + "tree = ast.fix_missing_locations(ast.Expression(body=node))\n"
                + "result = eval(compile(tree, '<manual>', 'eval'))\n");
        NamedExpr node = (NamedExpr)interpreter.get("node");
        assertEquals(7, node.getLineno());
        assertEquals(3, node.getCol_offset());
        assertEquals(42, interpreter.get("result").asInt());
        assertSame(interpreter.get("result"), interpreter.get("target"));
        assertTrue(node.refersDirectlyTo(node.getInternalTarget()));
        assertTrue(node.refersDirectlyTo(node.getInternalValue()));
    }
}
