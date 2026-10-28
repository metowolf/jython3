package org.python.core;

import java.util.LinkedHashMap;
import java.util.Map;
import junit.framework.TestCase;
import org.python.util.PythonInterpreter;

/** Native Java API acceptance for mapping display unpacking. */
public class MappingUnpackingTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testHelperCopiesAndOverwrites() {
        PyDictionary source = new PyDictionary();
        PyObject marker = new PyList();
        source.__setitem__(Py.newString("a"), marker);
        PyDictionary result = new PyDictionary();
        result.__setitem__(Py.newString("a"), Py.None);
        UnpackingSupport.mergeMapping(result, source);
        assertSame(marker, result.__getitem__(Py.newString("a")));
        result.__setitem__(Py.newString("b"), Py.True);
        assertEquals(1, source.__len__());
    }

    public void testHelperRejectsPairSequence() {
        PyList pairs = new PyList(new PyObject[] {
                new PyTuple(Py.newString("a"), Py.newInteger(1))});
        try {
            UnpackingSupport.mergeMapping(new PyDictionary(), pairs);
            fail("** requires a mapping, not dict.update's sequence-of-pairs protocol");
        } catch (PyException exception) {
            assertTrue(exception.match(Py.TypeError));
        }
    }

    public void testNativeNamespaceMapping() {
        PyStringMap namespace = new PyStringMap();
        namespace.__setitem__("a", Py.newInteger(1));
        PyDictionary result = new PyDictionary();
        UnpackingSupport.mergeMapping(result, namespace);
        assertEquals(1, result.__getitem__(Py.newString("a")).asInt());
    }

    public void testInterpreterReturnsNativeDictionary() {
        interpreter.exec("source = {'a': 1}\nresult = {**source, 'b': 2, **{'a': 3}}\n");
        PyObject result = interpreter.get("result");
        assertSame(PyDictionary.TYPE, result.getType());
        assertEquals(3, result.__getitem__(Py.newString("a")).asInt());
        assertEquals(2, result.__getitem__(Py.newString("b")).asInt());
        assertEquals(1, interpreter.get("source").__len__());
    }

    public void testJavaMapPreservesObjectIdentity() {
        Object marker = new Object();
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("marker", marker);
        interpreter.set("source", source);
        interpreter.exec("result = {**source, 'tail': 2}\n");
        assertSame(marker, interpreter.get("result").__getitem__(Py.newString("marker"))
                .__tojava__(Object.class));
        assertEquals(1, source.size());
    }

    public void testAstUsesNullKeyWithoutNullValue() {
        interpreter.exec("import ast\nnode = ast.parse('{**source}', mode='eval').body\n");
        org.python.antlr.ast.Dict node = (org.python.antlr.ast.Dict)interpreter.get("node");
        assertEquals(1, node.getInternalKeys().size());
        assertNull(node.getInternalKeys().get(0));
        assertNotNull(node.getInternalValues().get(0));
    }
}
