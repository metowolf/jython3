package org.python.core;

import junit.framework.TestCase;
import org.python.antlr.ast.ClassDef;
import org.python.antlr.ast.FunctionDef;
import org.python.antlr.ast.Subscript;
import org.python.util.PythonInterpreter;

/** Expression decorators execute on the JVM and retain Java/GC identity. */
public class DecoratorExpressionTest extends TestCase {
    private PythonInterpreter interpreter;

    public static class Bridge {
        public PyObject seen;

        public PyObject keep(PyObject value) {
            seen = value;
            return value;
        }
    }

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
        interpreter.exec("def identity(value): return value\n");
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testNativeFunctionAndClassIdentity() {
        Bridge bridge = new Bridge();
        interpreter.set("bridge", bridge);
        interpreter.exec("@[bridge.keep][0]\ndef f(): return 42\n");
        assertSame(bridge.seen, interpreter.get("f"));
        assertTrue(bridge.seen instanceof PyFunction);
        assertEquals(42, bridge.seen.__call__().asInt());
        interpreter.exec("@[bridge.keep][0]\nclass C(object): pass\n");
        assertSame(bridge.seen, interpreter.get("C"));
        assertTrue(bridge.seen instanceof PyType);
    }

    public void testThreadStateAndReplacementIdentity() {
        ThreadState state = Py.getThreadState();
        PyObject replacement = Py.java2py(new Object());
        PyObject decorator = new PyObject() {
            @Override
            public PyObject __call__(ThreadState actual, PyObject value) {
                assertSame(state, actual);
                assertTrue(value instanceof PyFunction);
                return replacement;
            }
        };
        interpreter.set("decorator", decorator);
        interpreter.exec("@[decorator][0]\ndef f(): pass\n");
        assertSame(replacement, interpreter.get("f"));
    }

    public void testDecoratedJavaInterfaceInvokedFromJava() {
        interpreter.exec("from java.lang import Runnable\nevents = []\n"
                + "@[identity][0]\nclass C(*[Runnable]):\n"
                + " def run(self): events.append('called')\nresult = C()\n");
        Object proxy = interpreter.get("result").__tojava__(Runnable.class);
        assertTrue(proxy instanceof Runnable);
        ((Runnable)proxy).run();
        assertEquals("['called']", interpreter.get("events").toString());
    }

    public void testParserUsesExistingExpressionAndDefinitionNodes() {
        interpreter.exec("import ast\n"
                + "f = ast.parse('@[identity][0]\\ndef f(): pass').body[0]\n"
                + "c = ast.parse('@[identity][0]\\nclass C(object): pass').body[0]\n");
        FunctionDef function = (FunctionDef)interpreter.get("f");
        ClassDef cls = (ClassDef)interpreter.get("c");
        assertTrue(function.getInternalDecorator_list().get(0) instanceof Subscript);
        assertTrue(cls.getInternalDecorator_list().get(0) instanceof Subscript);
        assertEquals(1, cls.getInternalDecorator_list().get(0).getCol_offset());
        assertEquals(4, cls.get_fields().length);
    }

    public void testSuspendedDecoratorArrayTraversal() {
        interpreter.exec("def gen():\n @[identity][0]\n @(yield 'next')\n"
                + " def f(value=(yield 'default')): return value\n yield f\n"
                + "iterator = gen()\nnext(iterator)\n");
        PyFrame frame = ((PyGenerator)interpreter.get("iterator")).gi_frame;
        PyObject decorator = interpreter.get("identity");
        boolean saved = false;
        for (Object local : frame.f_savedlocals) {
            if (local instanceof PyObject[]) {
                PyObject[] values = (PyObject[])local;
                if (values.length == 2 && values[0] == decorator && values[1] == null) {
                    saved = true;
                }
            }
        }
        assertTrue("partially evaluated decorator array is saved", saved);
        assertTrue(frame.refersDirectlyTo(decorator));
        assertEquals(23, frame.traverse((value, arg) -> value == decorator ? 23 : 0, null));
        interpreter.exec("assert iterator.send(identity) == 'default'\n"
                + "result = iterator.send(42)\niterator.close()\n");
        assertEquals(42, interpreter.get("result").__call__().asInt());
    }
}
