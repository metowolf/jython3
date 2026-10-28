package org.python.core;

import junit.framework.TestCase;
import org.python.antlr.ast.FormattedValue;
import org.python.antlr.ast.JoinedStr;
import org.python.util.PythonInterpreter;

public class FStringTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testAstSetterReferencesAreTraversed() {
        interpreter.exec("import ast\n"
                + "field = ast.FormattedValue(ast.Num(n=1), -1, None)\n"
                + "field.value = ast.Num(n=2)\n"
                + "field.format_spec = ast.JoinedStr([ast.Str(s=u'03d')])\n"
                + "joined = ast.JoinedStr([])\njoined.values = [field]\n"
                + "field.tag = object()\njoined.tag = object()\n");
        FormattedValue field = (FormattedValue)interpreter.get("field");
        JoinedStr joined = (JoinedStr)interpreter.get("joined");
        for (PyObject target : new PyObject[] {
                field.getInternalValue(), field.getInternalFormat_spec(), field.getDict()}) {
            assertTrue(field.refersDirectlyTo(target));
            assertEquals(17, field.traverse((object, arg) -> object == target ? 17 : 0, null));
        }
        for (PyObject target : new PyObject[] {field, joined.getDict()}) {
            assertTrue(joined.refersDirectlyTo(target));
            assertEquals(19, joined.traverse((object, arg) -> object == target ? 19 : 0, null));
        }
        assertFalse(field.refersDirectlyTo(null));
        assertFalse(joined.refersDirectlyTo(null));
    }

    public void testNativeRuntimeHelpers() {
        assertEquals("0007", FStringSupport.format(Py.newInteger(7), Py.newUnicode("04d"), -1)
                .getString());
        assertEquals("'\\u4e2d\\U0001f600'", FStringSupport.format(
                Py.newUnicode("\u4e2d\ud83d\ude00"), Py.newUnicode(""), 'a').getString());
        assertEquals("a7", FStringSupport.join(new PyObject[] {
                Py.newUnicode("a"), Py.newUnicode("7")}).getString());
        assertEquals("", FStringSupport.join(Py.EmptyObjects).getString());
    }

    public void testCompilerUsesNativeNodesAndUnicode() {
        interpreter.exec("value = 7\nresult = f'number={value:04d}'\n");
        PyObject result = interpreter.get("result");
        assertTrue(result instanceof PyUnicode);
        assertEquals("number=0007", result.asString());
        interpreter.exec("def outer():\n"
                + "    width = 4\n"
                + "    def inner(value):\n"
                + "        return f'{value:0{width}d}'\n"
                + "    return inner\n"
                + "result = outer()(9)\n");
        assertEquals("0009", interpreter.get("result").asString());
    }
}
