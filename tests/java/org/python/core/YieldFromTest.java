package org.python.core;

import junit.framework.TestCase;
import org.python.antlr.Visitor;
import org.python.antlr.ast.Name;
import org.python.antlr.ast.YieldFrom;
import org.python.util.PythonInterpreter;

public class YieldFromTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() { interpreter = new PythonInterpreter(); }
    @Override
    protected void tearDown() { interpreter.close(); }

    private PyGenerator generator() { return (PyGenerator)interpreter.get("iterator"); }

    public void testJavaIteratorReturnIdentityAndThreadState() {
        PyObject marker = Py.java2py(new Object());
        ThreadState thread = Py.getThreadState();
        PyIterator iterator = new PyIterator() {
            private int calls;
            @Override
            public PyObject __iternext__() {
                assertSame(thread, Py.getThreadState());
                if (calls++ == 0) return marker;
                stopException = Py.StopIterationValue(marker);
                return null;
            }
        };
        interpreter.set("source", iterator);
        interpreter.exec("def outer():\n return (yield from source)\niterator = outer()\n");
        assertSame(marker, generator().next());
        try {
            generator().next();
            fail("expected return");
        } catch (PyException exception) {
            assertTrue(exception.match(Py.StopIteration));
            assertSame(marker, YieldFromSupport.stopValue(exception));
        }
        assertNull(generator().gi_frame);
    }

    public void testDelegateSavedLocalTraversal() {
        interpreter.exec("def source():\n yield 1\ndef outer():\n yield from source()\n"
                + "iterator = outer()\nnext(iterator)\n");
        PyFrame frame = generator().gi_frame;
        PyObject delegate = generator().getYieldFrom();
        boolean found = false;
        for (Object value : frame.f_savedlocals) {
            if (value instanceof YieldFromSupport) {
                found = true;
                assertTrue(((YieldFromSupport)value).refersDirectlyTo(delegate));
                assertEquals(19, ((YieldFromSupport)value).traverse((object, arg) -> object == delegate ? 19 : 0, null));
            }
        }
        assertTrue(found);
        PyFrame isolated = new PyFrame(null, null, null, null);
        isolated.f_savedlocals = frame.f_savedlocals;
        assertTrue(isolated.refersDirectlyTo(delegate));
        assertEquals(23, isolated.traverse((object, arg) -> object == delegate ? 23 : 0, null));
        generator().close();
        assertNull(frame.f_yieldfrom);
        assertNull(frame.f_savedlocals);
    }

    public void testReturnValueSavedAcrossFinally() {
        PyObject marker = Py.java2py(new Object());
        interpreter.set("marker", marker);
        interpreter.exec("def outer():\n try:\n  return marker\n finally:\n  yield from [1, 2]\n"
                + "iterator = outer()\nnext(iterator)\n");
        PyFrame frame = new PyFrame(null, null, null, null);
        frame.f_savedlocals = generator().gi_frame.f_savedlocals;
        assertTrue(frame.refersDirectlyTo(marker));
        assertEquals(29, frame.traverse((object, arg) -> object == marker ? 29 : 0, null));
        assertEquals(2, generator().next().asInt());
        try {
            generator().next();
            fail("expected generator result");
        } catch (PyException exception) {
            assertSame(marker, YieldFromSupport.stopValue(exception));
        }
    }

    public void testStopValueGcIndependentOfArgs() {
        PyObject marker = Py.java2py(new Object());
        PyException stopped = Py.StopIterationValue(marker);
        stopped.normalize();
        PyBaseException value = (PyBaseException)stopped.value;
        value.setArgs(Py.EmptyTuple);
        assertTrue(value.refersDirectlyTo(marker));
        assertEquals(31, value.traverse((object, arg) -> object == marker ? 31 : 0, null));
        assertSame(marker, value.__getattr__("value"));
        assertSame(marker, YieldFromSupport.stopValue(stopped));
    }

    public void testRawJavaIterationDropsConsumedReturnValue() {
        interpreter.exec("def outer():\n yield 1\n return 42\niterator = outer()\n");
        assertEquals(1, generator().__iternext__().asInt());
        assertNull(generator().__iternext__());
        assertNull(generator().__iternext__());
        try {
            generator().next();
            fail("exhausted");
        } catch (PyException exception) {
            assertSame(Py.None, YieldFromSupport.stopValue(exception));
        }
    }

    public void testAstVisitorLocationsAndGc() throws Exception {
        interpreter.exec("import ast\nnode = ast.parse('def f():\\n yield from source\\n').body[0].body[0].value\n");
        YieldFrom node = (YieldFrom)interpreter.get("node");
        assertEquals(2, node.getLineno());
        assertEquals(1, node.getCol_offset());
        assertSame(node, node.getInternalValue().getParent());
        final int[] calls = {0};
        node.accept(new Visitor() {
            @Override
            public Object visitName(Name name) {
                assertEquals("source", name.getInternalId());
                calls[0]++;
                return null;
            }
        });
        assertEquals(1, calls[0]);
        PyObject dictionary = node.fastGetDict();
        for (PyObject reference : new PyObject[] {node.getInternalValue(), dictionary}) {
            assertTrue(node.refersDirectlyTo(reference));
            assertEquals(37, node.traverse((object, arg) -> object == reference ? 37 : 0, null));
        }
    }

    public void testStopTupleIsSingleArgument() {
        PyTuple marker = new PyTuple(Py.newInteger(1), Py.newInteger(2));
        PyException exception = Py.StopIterationValue(marker);
        exception.normalize();
        assertSame(marker, YieldFromSupport.stopValue(exception));
        PyTuple args = (PyTuple)((PyBaseException)exception.value).args;
        assertEquals(1, args.__len__());
        assertSame(marker, args.pyget(0));
    }
}
