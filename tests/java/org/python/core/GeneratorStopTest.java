package org.python.core;

import junit.framework.TestCase;
import org.python.util.PythonInterpreter;

public class GeneratorStopTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() { interpreter = new PythonInterpreter(); }

    @Override
    protected void tearDown() { interpreter.close(); }

    private PyGenerator generator() { return (PyGenerator)interpreter.get("iterator"); }

    private PyBaseException converted(Runnable operation, PyObject original) {
        try {
            operation.run();
            fail("expected RuntimeError, not null or StopIteration");
        } catch (PyException exception) {
            assertTrue(exception.match(Py.RuntimeError));
            PyBaseException error = (PyBaseException)exception.value;
            assertEquals("generator raised StopIteration", error.__str__().toString());
            assertSame(original, error.getCause());
            assertSame(original, error.getContext());
            assertSame(Py.True, error.getSuppressContext());
            return error;
        }
        return null;
    }

    public void testRawJavaIterationDoesNotSilentlyStop() {
        PyObject marker = Py.java2py(new Object());
        PyObject original = Py.StopIteration.__call__(marker);
        interpreter.set("original", original);
        interpreter.exec("def gen():\n yield 1\n raise original\niterator = gen()\n");
        assertEquals(1, generator().__iternext__().asInt());
        converted(() -> generator().__iternext__(), original);
        assertNull(generator().stopException);
        assertNull(generator().gi_frame);
        assertFalse(generator().gi_running);
        assertNull(generator().__iternext__());
        assertSame(marker, ((PyBaseException)original).stopIterationValue);
    }

    public void testJavaCallbackAndThreadState() {
        ThreadState state = Py.getThreadState();
        PyException original = Py.StopIterationValue(Py.newInteger(42));
        original.normalize();
        interpreter.set("callback", new PyObject() {
            @Override
            public PyObject __call__(ThreadState thread) {
                assertSame(state, thread);
                throw original;
            }
        });
        interpreter.exec("def gen():\n yield callback()\niterator = gen()\n");
        PyFrame frame = state.frame;
        PyException handled = state.exception;
        converted(() -> generator().__iternext__(state), original.value);
        assertSame(frame, state.frame);
        assertSame(handled, state.exception);
    }

    public void testCauseContextAndTracebackAreGcVisible() {
        interpreter.exec("original = StopIteration(42)\ndef gen():\n raise original\n yield\n"
                + "iterator = gen()\n");
        PyBaseException original = (PyBaseException)interpreter.get("original");
        PyBaseException error = converted(() -> generator().next(), original);
        assertTrue(error.refersDirectlyTo(original));
        assertEquals(19, error.traverse((object, arg) -> object == original ? 19 : 0, null));
        PyObject traceback = original.getTraceback();
        assertTrue(traceback instanceof PyTraceback);
        assertTrue(original.refersDirectlyTo(traceback));
        assertEquals(23, original.traverse((object, arg) -> object == traceback ? 23 : 0, null));
    }

    public void testDelegatedFailureClearsSavedFrameState() {
        interpreter.exec("original = StopIteration(42)\ndef inner():\n yield 1\n raise original\n"
                + "def outer():\n return (yield from inner())\niterator = outer()\nnext(iterator)\n");
        PyFrame frame = generator().gi_frame;
        assertNotNull(frame.f_yieldfrom);
        assertNotNull(frame.f_savedlocals);
        converted(() -> generator().next(), interpreter.get("original"));
        assertNull(frame.f_yieldfrom);
        assertNull(frame.f_savedlocals);
        assertNull(generator().gi_frame);
        assertNull(generator().stopException);
        assertSame(Py.None, frame.getGeneratorInput());
    }

    public void testNativeIteratorCompletionIsStillNormal() {
        PyObject marker = Py.java2py(new Object());
        interpreter.set("source", new PyIterator() {
            @Override
            public PyObject __iternext__() {
                stopException = Py.StopIterationValue(marker);
                return null;
            }
        });
        interpreter.exec("def gen():\n return (yield from source)\niterator = gen()\n");
        try {
            generator().next();
            fail("expected normal return");
        } catch (PyException exception) {
            assertTrue(exception.match(Py.StopIteration));
            assertSame(marker, YieldFromSupport.stopValue(exception));
        }
    }

    public void testFutureFlagRoundTrip() {
        int flag = CodeFlag.CO_FUTURE_GENERATOR_STOP.flag;
        assertEquals(0x800000, flag);
        CompilerFlags flags = CompilerFlags.getCompilerFlags(flag, null);
        assertTrue(flags.isFlagSet(CodeFlag.CO_FUTURE_GENERATOR_STOP));
        assertEquals(flag, flags.toBits() & flag);
        interpreter.exec("from __future__ import generator_stop\n"
                + "def gen():\n raise StopIteration(42)\n yield\niterator = gen()\n");
        assertTrue(generator().gi_code instanceof PyBaseCode);
        assertFalse(((PyBaseCode)generator().gi_code).co_flags
                .isFlagSet(CodeFlag.CO_FUTURE_GENERATOR_STOP));
        interpreter.exec("eval(compile('def gen():\\n yield\\n', '<flags>', 'exec', 0x800000, True))\n"
                + "iterator = gen()\n");
        assertTrue(((PyBaseCode)generator().gi_code).co_flags
                .isFlagSet(CodeFlag.CO_FUTURE_GENERATOR_STOP));
    }
}
