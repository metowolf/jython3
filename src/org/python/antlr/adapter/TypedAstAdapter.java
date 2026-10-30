package org.python.antlr.adapter;

import java.util.ArrayList;
import java.util.List;
import org.python.core.Py;
import org.python.core.PyObject;

/** Shared adapter for non-expression AST nodes. */
public final class TypedAstAdapter implements AstAdapter {
    private final Class<? extends PyObject> type;

    public TypedAstAdapter(Class<? extends PyObject> type) {
        this.type = type;
    }

    public Object py2ast(PyObject value) {
        if (value == null || value == Py.None) return null;
        if (!type.isInstance(value)) throw Py.TypeError("expected " + type.getSimpleName());
        return value;
    }

    public PyObject ast2py(Object value) {
        return value == null ? Py.None : (PyObject)value;
    }

    public List iter2ast(PyObject values) {
        List<PyObject> result = new ArrayList<PyObject>();
        if (values != Py.None) {
            for (PyObject value : values.asIterable()) result.add((PyObject)py2ast(value));
        }
        return result;
    }
}
