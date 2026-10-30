package org.python.core;

/** A builtin classmethod with a keyword-capable argument array. */
public abstract class PyBuiltinClassMethod extends PyBuiltinMethod {
    protected PyBuiltinClassMethod(String name) {
        super(name);
    }

    protected PyBuiltinClassMethod(PyType type, PyObject self, Info info) {
        super(type, self, info);
    }

    @Override
    public PyMethodDescr makeDescriptor(PyType type) {
        return new PyClassMethodDescr(type, this);
    }
}
