package org.python.core;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import junit.framework.TestCase;
import org.python.util.PythonInterpreter;

/** Native API, call ABI and suspended-accumulator GC acceptance. */
public class CallUnpackingTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
        interpreter.exec("def collect(*args, **kwargs):\n return args, kwargs\n");
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testHelperUsesExistingCallAbi() {
        CallUnpackingSupport call = new CallUnpackingSupport(interpreter.get("collect"));
        call.add(Py.newInteger(1));
        call.extend(new PyTuple(Py.newInteger(2)));
        call.addKeywords(new PyObject[] {Py.newInteger(3)}, new String[] {"a"});
        PyObject result = call.call(Py.getThreadState());
        assertTrue(result.__getitem__(0) instanceof PyTuple);
        assertTrue(result.__getitem__(1) instanceof PyDictionary);
        assertEquals("(1, 2)", result.__getitem__(0).toString());
        assertEquals(3, result.__getitem__(1).__getitem__(Py.newString("a")).asInt());
    }

    public void testHelperRejectsDuplicateMapping() {
        CallUnpackingSupport call = new CallUnpackingSupport(interpreter.get("collect"));
        PyDictionary mapping = new PyDictionary();
        mapping.__setitem__("a", Py.None);
        call.merge(mapping);
        try {
            call.merge(mapping);
            fail("duplicate keywords must not overwrite");
        } catch (PyException exception) {
            assertTrue(exception.match(Py.TypeError));
        }
    }

    public void testSavedAccumulatorTraversal() {
        PyObject callable = interpreter.get("collect");
        PyObject deferred = new PyList();
        PyObject value = new PyList();
        CallUnpackingSupport call = new CallUnpackingSupport(callable);
        call.defer(deferred);
        call.addKeywords(new PyObject[] {value}, new String[] {"a"});
        PyFrame frame = new PyFrame(null, new PyStringMap());
        frame.f_savedlocals = new Object[] {call};
        for (PyObject target : new PyObject[] {callable, deferred, value}) {
            assertTrue(call.refersDirectlyTo(target));
            assertTrue(frame.refersDirectlyTo(target));
            assertEquals(29, frame.traverse((object, arg) -> object == target ? 29 : 0, null));
        }
        assertFalse(call.refersDirectlyTo(null));
    }

    public void testJavaIterableAndMapIdentity() {
        Object marker = new Object();
        Iterable<Object> source = () -> Arrays.asList(marker).iterator();
        Map<String, Object> mapping = new LinkedHashMap<>();
        mapping.put("marker", marker);
        interpreter.set("source", source);
        interpreter.set("mapping", mapping);
        interpreter.exec("result = collect(*source, *[], **mapping, **{})\n");
        PyObject result = interpreter.get("result");
        assertSame(marker, result.__getitem__(0).__getitem__(0).__tojava__(Object.class));
        assertSame(marker, result.__getitem__(1).__getitem__(Py.newString("marker"))
                .__tojava__(Object.class));
        assertEquals(1, mapping.size());
    }

    public void testJavaReceiverAndConstructor() {
        interpreter.exec("from java.lang import Math, StringBuilder\n"
                + "maximum = Math.max(*[3], *[7])\n"
                + "builder = StringBuilder(*[], *['ab'])\n"
                + "builder.append(*[], *['cd'])\n");
        assertEquals(7, interpreter.get("maximum").asInt());
        assertEquals("abcd", interpreter.get("builder").toString());
    }

    public void testParserUsesModernEntriesAndKeepsLegacyFields() {
        interpreter.exec("import ast\nnode = ast.parse('collect(*a, *b, **c, **d)', mode='eval').body\n");
        org.python.antlr.ast.Call node = (org.python.antlr.ast.Call)interpreter.get("node");
        assertEquals(2, node.getInternalArgs().size());
        assertTrue(node.getInternalArgs().get(0) instanceof org.python.antlr.ast.Starred);
        assertEquals(2, node.getInternalKeywords().size());
        assertNull(node.getInternalKeywords().get(0).getInternalArg());
        assertNull(node.getInternalStarargs());
        assertNull(node.getInternalKwargs());
    }
}
