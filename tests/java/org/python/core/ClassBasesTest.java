package org.python.core;

import java.util.Arrays;
import junit.framework.TestCase;
import org.python.antlr.ast.ClassDef;
import org.python.antlr.ast.Starred;
import org.python.util.PythonInterpreter;

/** Native class compilation, Java inheritance and suspended-frame GC checks. */
public class ClassBasesTest extends TestCase {
    private PythonInterpreter interpreter;

    @Override
    protected void setUp() {
        interpreter = new PythonInterpreter();
        interpreter.exec("class A(object): pass\nclass B(object): pass\n");
    }

    @Override
    protected void tearDown() {
        interpreter.close();
    }

    public void testNativeClassAndBaseIdentity() {
        interpreter.exec("class C(*[A], *[B]): pass\nresult = C()\n");
        PyObject cls = interpreter.get("C");
        assertTrue(cls instanceof PyType);
        PyObject bases = cls.__getattr__("__bases__");
        assertSame(interpreter.get("A"), bases.__getitem__(0));
        assertSame(interpreter.get("B"), bases.__getitem__(1));
        assertSame(cls, interpreter.get("result").getType());
    }

    public void testSourceTupleAndMetaclassBaseTupleRetained() {
        interpreter.exec("source = (A, B)\nclass C(*source): pass\n");
        PyObject source = interpreter.get("source");
        assertSame(interpreter.get("A"), source.__getitem__(0));
        assertSame(interpreter.get("B"), source.__getitem__(1));
        assertEquals(source, interpreter.get("C").__getattr__("__bases__"));
    }

    public void testJavaIterableOfPythonClasses() {
        PyObject a = interpreter.get("A");
        PyObject b = interpreter.get("B");
        Iterable<PyObject> bases = () -> Arrays.asList(a, b).iterator();
        interpreter.set("bases", bases);
        interpreter.exec("class C(*bases): pass\n");
        PyObject result = interpreter.get("C").__getattr__("__bases__");
        assertSame(a, result.__getitem__(0));
        assertSame(b, result.__getitem__(1));
    }

    public void testJavaInterfaceInvokedFromJava() {
        interpreter.exec("from java.lang import Runnable\n"
                + "events = []\nclass C(*[Runnable], *[]):\n"
                + " def run(self): events.append('called')\nresult = C()\n");
        Object proxy = interpreter.get("result").__tojava__(Runnable.class);
        assertTrue(proxy instanceof Runnable);
        ((Runnable)proxy).run();
        assertEquals("['called']", interpreter.get("events").toString());
    }

    public void testParserRetainsLegacyFieldsAndModernBases() {
        interpreter.exec("import ast\nnode = ast.parse('class C(A, *[B]): pass').body[0]\n");
        ClassDef node = (ClassDef)interpreter.get("node");
        assertEquals(4, node.get_fields().length);
        assertEquals(2, node.getInternalBases().size());
        assertTrue(node.getInternalBases().get(1) instanceof Starred);
        assertEquals(11, node.getInternalBases().get(1).getCol_offset());
    }

    public void testSavedArrayTraversalSkipsNullsAndStopsEarly() {
        PyObject first = new PyList();
        PyObject second = new PyList();
        PyFrame frame = new PyFrame(null, new PyStringMap());
        frame.f_savedlocals = new Object[] {null, new PyObject[] {null, first, second}};
        assertTrue(frame.refersDirectlyTo(first));
        assertTrue(frame.refersDirectlyTo(second));
        assertFalse(frame.refersDirectlyTo(new PyList()));
        assertFalse(frame.refersDirectlyTo(null));
        int[] visited = {0};
        assertEquals(37, frame.traverse((value, arg) -> {
            assertNotNull(value);
            if (value == first) {
                visited[0]++;
                return 37;
            }
            if (value == second) fail("visitor must stop before second array element");
            return 0;
        }, null));
        assertEquals(1, visited[0]);
        assertEquals(41, frame.traverse((value, arg) -> value == second ? 41 : 0, null));
    }

    public void testSuspendedDecoratorAndBasesAreTraversed() {
        interpreter.exec("def decorate():\n def apply(cls): return cls\n return apply\n"
                + "def gen():\n @decorate()\n class C(*[A], *(yield 'pause')): pass\n yield C\n"
                + "iterator = gen()\nnext(iterator)\n");
        PyGenerator generator = (PyGenerator)interpreter.get("iterator");
        PyFrame frame = generator.gi_frame;
        PyObject decorator = null;
        PyList builder = null;
        for (Object saved : frame.f_savedlocals) {
            if (saved instanceof PyObject[]) {
                for (PyObject value : (PyObject[])saved) {
                    if (value instanceof PyFunction) decorator = value;
                }
            } else if (saved instanceof PyList) {
                PyList list = (PyList)saved;
                if (list.__len__() == 1 && list.pyget(0) == interpreter.get("A")) builder = list;
            }
        }
        assertNotNull("evaluated decorator is saved across base yield", decorator);
        assertNotNull("expanded bases are saved across yield", builder);
        for (PyObject target : new PyObject[] {decorator, builder}) {
            assertTrue(frame.refersDirectlyTo(target));
            assertEquals(31, frame.traverse((value, arg) -> value == target ? 31 : 0, null));
        }
        interpreter.exec("result = iterator.send([B])\niterator.close()\n");
        assertEquals("(<class '__main__.A'>, <class '__main__.B'>)",
                interpreter.get("result").__getattr__("__bases__").toString());
    }
}
