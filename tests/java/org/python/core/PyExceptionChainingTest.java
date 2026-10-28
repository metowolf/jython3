package org.python.core;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import junit.framework.TestCase;
import org.python.antlr.ast.Raise;
import org.python.util.PythonInterpreter;

public class PyExceptionChainingTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testExceptionReferencesAreTraversed() {
        interpreter.exec("cause = ValueError('cause')\ncontext = TypeError('context')\n"
                + "try:\n    raise RuntimeError('outer') from cause\n"
                + "except RuntimeError as caught:\n    error = caught\n"
                + "error.__context__ = context\n");
        PyBaseException error = (PyBaseException)interpreter.get("error");
        Set<PyObject> visited = Collections.newSetFromMap(
                new IdentityHashMap<PyObject, Boolean>());
        assertEquals(0, error.traverse((object, arg) -> {
            visited.add(object);
            return 0;
        }, null));
        for (PyObject link : new PyObject[] {
                error.getCause(), error.getContext(), error.getTraceback()}) {
            assertTrue(visited.contains(link));
            assertTrue(error.refersDirectlyTo(link));
            assertEquals(17, error.traverse((object, arg) -> object == link ? 17 : 0, null));
        }
        assertFalse(error.refersDirectlyTo(null));
    }

    public void testFrameHandlerIsTraversed() {
        PyException exception = PyException.doRaise(Py.ValueError, null, null);
        PyFrame frame = new PyFrame(null, null);
        frame.handledException = exception;
        assertTrue(frame.refersDirectlyTo(exception.value));
        assertEquals(23, frame.traverse(
                (object, arg) -> object == exception.value ? 23 : 0, null));
        frame.handledException = null;
        assertFalse(frame.refersDirectlyTo(exception.value));
    }

    public void testLegacyRaiseConstructorAndFactory() {
        Raise node = new Raise(Py.None, Py.None, Py.None);
        assertSame(Py.None, node.getCause());
        PyException exception = Py.makeException(Py.ValueError, Py.newString("legacy"));
        exception.normalize();
        assertTrue(exception.value instanceof PyBaseException);
        assertSame(Py.None, ((PyBaseException)exception.value).getCause());
    }

    public void testNativeDisplayHandlesLongCycles() {
        PyBaseException first = (PyBaseException)Py.ValueError.__call__(Py.newString("first"));
        PyBaseException previous = first;
        for (int i = 0; i < 1500; i++) {
            PyBaseException next = (PyBaseException)Py.ValueError.__call__(Py.newString("next"));
            next.setCause(previous);
            previous = next;
        }
        first.setCause(previous);
        String text = Py.exceptionToString(previous.getType(), previous, Py.None);
        assertTrue(text.contains("ValueError: first"));
        assertEquals(1500, text.split("direct cause", -1).length - 1);
    }
}
