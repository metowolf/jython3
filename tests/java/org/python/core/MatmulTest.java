package org.python.core;

import junit.framework.TestCase;
import org.python.antlr.adapter.AstAdapters;
import org.python.antlr.ast.Attribute;
import org.python.antlr.ast.AugAssign;
import org.python.antlr.ast.operatorType;
import org.python.antlr.base.expr;
import org.python.antlr.op.MatMult;
import org.python.util.PythonInterpreter;

/** Matrix syntax and dispatch must execute natively, preserving Java identity. */
public class MatmulTest extends TestCase {
    private PythonInterpreter interpreter;

    public static class MatrixBridge {
        public PyObject seen;
        public PyObject __matmul__(PyObject other) {
            seen = other;
            return other;
        }
        public PyObject __imatmul__(PyObject other) {
            seen = other;
            return other;
        }
    }

    public static class ReflectedBridge {
        public PyObject __rmatmul__(PyObject other) {
            return other;
        }
    }

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
        interpreter.exec("class Matrix(object):\n def __matmul__(self, other): return other\n");
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testNativeIdentityAndDirectHelper() {
        PyObject right = Py.java2py(new Object());
        interpreter.set("right", right);
        interpreter.exec("left = Matrix()\nresult = left @ right\n");
        assertTrue(interpreter.get("left") instanceof PyObjectDerived);
        assertSame(right, interpreter.get("result"));
        assertSame(right, MatmulSupport.matmul(interpreter.get("left"), right));
        assertSame(right, MatmulSupport.imatmul(interpreter.get("left"), right));
    }

    public void testReflectedJavaMethods() {
        MatrixBridge bridge = new MatrixBridge();
        PyObject right = Py.java2py(new Object());
        interpreter.set("bridge", bridge);
        interpreter.set("right", right);
        interpreter.exec("result = bridge @ right\n");
        assertSame(right, bridge.seen);
        assertSame(right, interpreter.get("result"));
        interpreter.exec("bridge @= right\n");
        assertSame(right, interpreter.get("bridge"));
        interpreter.set("reflected", new ReflectedBridge());
        interpreter.exec("result = right @ reflected\n");
        assertSame(right, interpreter.get("result"));
    }

    public void testThreadStateCallingConvention() {
        ThreadState expected = Py.getThreadState();
        PyObject result = Py.java2py(new Object());
        PyObject callable = new PyObject() {
            @Override
            public PyObject __call__(ThreadState actual, PyObject other) {
                assertSame(expected, actual);
                assertSame(Py.None, other);
                return result;
            }
        };
        interpreter.set("callback", callable);
        interpreter.exec("class C(object):\n __matmul__ = callback\nvalue = C() @ None\n");
        assertSame(result, interpreter.get("value"));
    }

    private void assertSavedAndTraversed(PyFrame frame, PyObject object) {
        boolean saved = false;
        for (Object local : frame.f_savedlocals) {
            if (local == object) saved = true;
        }
        assertTrue("operand must be saved as a typed local", saved);
        assertTrue(frame.refersDirectlyTo(object));
        assertEquals(29, frame.traverse((value, arg) -> value == object ? 29 : 0, null));
    }

    public void testSuspendedBinaryOperandTraversal() {
        interpreter.exec("left = Matrix()\ndef gen():\n yield left @ (yield 1)\n"
                + "iterator = gen()\nnext(iterator)\n");
        PyFrame frame = ((PyGenerator)interpreter.get("iterator")).gi_frame;
        assertSavedAndTraversed(frame, interpreter.get("left"));
        interpreter.exec("assert iterator.send(42) == 42\niterator.close()\n");
    }

    public void testSuspendedAttributeAndLegacyAugment() {
        interpreter.exec("class Box(object): pass\nbox = Box()\nbox.value = Matrix()\n"
                + "left = box.value\ndef gen():\n box.value @= (yield 1)\n yield box.value\n"
                + "iterator = gen()\nnext(iterator)\n");
        PyFrame frame = ((PyGenerator)interpreter.get("iterator")).gi_frame;
        assertSavedAndTraversed(frame, interpreter.get("box"));
        assertSavedAndTraversed(frame, interpreter.get("left"));
        interpreter.exec("assert iterator.send(42) == 42\niterator.close()\n"
                + "box.value = 1\ndef old():\n box.value += (yield 1)\n yield box.value\n"
                + "iterator = old()\nnext(iterator)\nassert iterator.send(2) == 3\niterator.close()\n");
    }

    public void testAstAdaptersAndUnchangedParents() {
        assertEquals(13, operatorType.MatMult.ordinal());
        assertEquals(operatorType.MatMult, AstAdapters.py2operator(new MatMult()));
        assertTrue(AstAdapters.operator2py(operatorType.MatMult) instanceof MatMult);
        interpreter.exec("import ast\ntree = ast.parse('box.value @= other')\n"
                + "node = tree.body[0]\nnode.target.ctx = ast.Store()\n");
        AugAssign node = (AugAssign)interpreter.get("node");
        Attribute target = (Attribute)node.getInternalTarget();
        expr value = target.getInternalValue();
        Object parent = value.getParent();
        interpreter.exec("compile(tree, '<manual>', 'exec')\n");
        assertSame(target, node.getInternalTarget());
        assertSame(parent, value.getParent());
        assertEquals(org.python.antlr.ast.expr_contextType.Store, target.getInternalCtx());
    }
}
