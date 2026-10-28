package org.python.core;

import java.util.Arrays;
import java.util.Iterator;
import junit.framework.TestCase;
import org.python.antlr.ast.Starred;
import org.python.util.PythonInterpreter;

/** Exercise the JVM implementation without the optional CPython launcher. */
public class UnpackingTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testNativeHelpersReturnFreshList() {
        PyTuple source = new PyTuple(Py.newInteger(1), Py.newInteger(2), Py.newInteger(3));
        PyObject[] values = UnpackingSupport.unpack(source, 1, 1);
        assertEquals(1, values[0].asInt());
        assertTrue(values[1] instanceof PyList);
        assertEquals("[2]", values[1].toString());
        assertEquals(3, values[2].asInt());
        assertEquals("(1, 2, 3)", source.toString());
        PyObject[] again = UnpackingSupport.unpack(source, 1, 1);
        assertNotSame(values[1], again[1]);
        assertEquals(0, UnpackingSupport.unpack(Py.EmptyTuple, 0, 0)[0].__len__());
    }

    public void testNativeHelperInsufficientInput() {
        try {
            UnpackingSupport.unpack(new PyTuple(Py.newInteger(1)), 1, 1);
            fail("expected ValueError");
        } catch (PyException exception) {
            assertTrue(exception.match(Py.ValueError));
            assertTrue(exception.toString().contains("expected at least 2, got 1"));
        }
    }

    public void testDisplayHelpers() {
        PyTuple source = new PyTuple(Py.newInteger(1), Py.newInteger(2));
        PyList list = new PyList();
        UnpackingSupport.extendList(list, source);
        UnpackingSupport.extendList(list, source);
        assertEquals("[1, 2, 1, 2]", list.toString());
        PySet set = new PySet();
        UnpackingSupport.extendSet(set, source);
        UnpackingSupport.addSet(set, Py.newInteger(2));
        assertEquals(2, set.__len__());
    }

    public void testCompilerProducesNativeObjects() {
        interpreter.exec("a, *rest, z = [1, 2, 3, 4]\n"
                + "items = [a, *rest, z]\ntup = (*items,)\nunique = {*items}\n");
        assertTrue(interpreter.get("rest") instanceof PyList);
        assertTrue(interpreter.get("tup") instanceof PyTuple);
        assertTrue(interpreter.get("unique") instanceof PySet);
        assertEquals("[1, 2, 3, 4]", interpreter.get("items").toString());
    }

    public void testJavaIterableRetainsObjectIdentity() {
        Object marker = new Object();
        Iterable<Object> source = new Iterable<Object>() {
            @Override
            public Iterator<Object> iterator() {
                return Arrays.asList(marker, "tail").iterator();
            }
        };
        interpreter.set("source", source);
        interpreter.exec("first, *rest = source\nitems = [*source]\n");
        assertSame(marker, interpreter.get("first").__tojava__(Object.class));
        assertSame(marker, interpreter.get("items").__getitem__(0).__tojava__(Object.class));
        assertEquals("tail", interpreter.get("rest").__getitem__(0).asString());
    }

    public void testAstSetterReferencesAreTraversed() {
        interpreter.exec("import ast\n"
                + "star = ast.Starred(ast.Name(id='old', ctx=ast.Load()), ast.Load())\n"
                + "star.value = ast.Name(id='new', ctx=ast.Load())\nstar.tag = object()\n");
        Starred star = (Starred)interpreter.get("star");
        for (PyObject target : new PyObject[] {star.getInternalValue(), star.getDict()}) {
            assertTrue(star.refersDirectlyTo(target));
            assertEquals(23, star.traverse((object, arg) -> object == target ? 23 : 0, null));
        }
        assertFalse(star.refersDirectlyTo(null));
    }
}
