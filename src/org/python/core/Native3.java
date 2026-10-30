package org.python.core;

import java.io.File;

/** Opt-in native Python 3 source roots, leaving the legacy stdlib in its own dialect. */
public final class Native3 {
    private Native3() {}

    public static boolean source(String filename) {
        String roots = System.getProperty("python.native3.path", "");
        if (roots.isEmpty() || filename == null || filename.startsWith("<")) {
            return false;
        }
        java.nio.file.Path file = new File(filename).toPath().toAbsolutePath().normalize();
        for (String root : roots.split(java.util.regex.Pattern.quote(File.pathSeparator))) {
            if (!root.isEmpty() && file.startsWith(new File(root).toPath().toAbsolutePath().normalize())) {
                return true;
            }
        }
        return false;
    }

    public static void configure(String filename, CompilerFlags flags) {
        if (source(filename)) {
            flags.setFlag(CodeFlag.CO_NATIVE3);
        }
        if (flags.isFlagSet(CodeFlag.CO_NATIVE3)) {
            flags.setFlag(CodeFlag.CO_FUTURE_PRINT_FUNCTION);
            flags.setFlag(CodeFlag.CO_FUTURE_UNICODE_LITERALS);
            flags.setFlag(CodeFlag.CO_FUTURE_ABSOLUTE_IMPORT);
            flags.setFlag(CodeFlag.CO_FUTURE_DIVISION);
        }
    }

    public static boolean frame(PyFrame frame) {
        return frame != null && frame.f_code != null
                && frame.f_code.co_flags.isFlagSet(CodeFlag.CO_NATIVE3);
    }

    public static void setupAnnotations(PyFrame frame) {
        if (frame.f_locals.__finditem__("__annotations__") == null) {
            frame.f_locals.__setitem__("__annotations__", new PyDictionary());
        }
    }

    public static void setAnnotation(PyFrame frame, String name, PyObject value) {
        frame.f_locals.__getitem__(Py.newString("__annotations__")).__setitem__(name, value);
    }

    public static PyObject integerFromBytes(PyType type, PyObject[] args, String[] keywords) {
        int positional = args.length - keywords.length;
        if (positional > 2) throw Py.TypeError("from_bytes() takes at most 2 positional arguments");
        ArgParser ap = new ArgParser("from_bytes", args, keywords,
                new String[] {"bytes", "byteorder", "signed"}, 1);
        PyObject source = ap.getPyObject(0);
        PyObject order = ap.getPyObject(1, Py.newUnicode("big"));
        if (!(order instanceof PyString)) throw Py.TypeError("byteorder must be a string");
        String byteorder = order.toString();
        if (!byteorder.equals("big") && !byteorder.equals("little")) {
            throw Py.ValueError("byteorder must be either 'little' or 'big'");
        }
        if (source instanceof PyUnicode || source.isIndex()) {
            throw Py.TypeError("cannot convert value to bytes");
        }
        PyByteArray data = new PyByteArray(source);
        byte[] bytes = new byte[data.__len__()];
        for (int i = 0; i < bytes.length; i++) {
            bytes[byteorder.equals("big") ? i : bytes.length - 1 - i] = (byte)data.intAt(i);
        }
        java.math.BigInteger value = bytes.length == 0 ? java.math.BigInteger.ZERO
                : ap.getPyObject(2, Py.False).__nonzero__() ? new java.math.BigInteger(bytes)
                : new java.math.BigInteger(1, bytes);
        PyObject result = new PyLong(value).__int__();
        if (type == PyInteger.TYPE) return result;
        if (type == PyLong.TYPE) return new PyLong(value);
        return type.__call__(result);
    }

    public static PyObject builtins() {
        return imp.importName("_native3_builtins", true).__getattr__("namespace");
    }
    /** Python 3 class construction: select the metaclass before executing the body. */
    public static PyObject makeClass(String name, PyObject[] bases, PyBaseCode code,
            PyObject[] closure, PyObject keywords) {
        PyObject options = keywords == null ? new PyDictionary() : keywords;
        PyObject metaclass = options.__finditem__("metaclass");
        if (metaclass != null) options.__delitem__("metaclass");
        else metaclass = bases.length == 0 ? PyType.TYPE : bases[0].getType();
        if (metaclass instanceof PyType) {
            metaclass = PyType.findMostDerivedMetatype(bases, (PyType)metaclass);
        }
        ThreadState state = Py.getThreadState();
        PyObject className = Py.newUnicode(name);
        PyTuple baseTuple = new PyTuple(bases);
        PyObject prepare = metaclass.__findattr__("__prepare__");
        PyObject namespace;
        if (prepare == null) {
            namespace = new PyDictionary();
        } else {
            CallUnpackingSupport call = new CallUnpackingSupport(prepare);
            call.add(className);
            call.add(baseTuple);
            call.merge(options);
            namespace = call.call(state);
            if (namespace.__findattr__("__getitem__") == null
                    || namespace.__findattr__("__setitem__") == null) {
                throw Py.TypeError("__prepare__() must return a mapping");
            }
        }
        PyFrame frame = new PyFrame(code, namespace, state.frame.f_globals, null);
        code.call(state, frame, new PyTuple(closure));
        PyObject cell = namespace.__finditem__("__classcell__");
        if (cell != null) namespace.__delitem__("__classcell__");
        CallUnpackingSupport call = new CallUnpackingSupport(metaclass);
        call.add(className);
        call.add(baseTuple);
        call.add(namespace);
        call.merge(options);
        PyObject result = call.call(state);
        if (cell instanceof PyCell) ((PyCell)cell).ob_ref = result;
        return result;
    }

}
