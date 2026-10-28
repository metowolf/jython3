package org.python.core;

import java.util.ArrayList;
import java.util.List;

/** Native JVM operations for starred assignment and iterable displays. */
public final class UnpackingSupport {
    private UnpackingSupport() {}

    /** Unpack before fixed values, a fresh list, and after fixed values. */
    public static PyObject[] unpack(PyObject source, int before, int after) {
        if (before < 0 || after < 0 || (long) before + after + 1 > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid unpacking counts");
        }
        PyObject iterator = source.__iter__();
        PyObject[] result = new PyObject[before + after + 1];
        for (int i = 0; i < before; i++) {
            PyObject value = iterator.__iternext__();
            if (value == null) {
                throw tooFew(before + after, i);
            }
            result[i] = value;
        }
        List<PyObject> rest = new ArrayList<>();
        for (PyObject value : iterator.asIterable()) {
            rest.add(value);
        }
        int split = rest.size() - after;
        if (split < 0) {
            throw tooFew(before + after, before + rest.size());
        }
        for (int i = 0; i < after; i++) {
            result[before + 1 + i] = rest.get(split + i);
        }
        rest.subList(split, rest.size()).clear();
        result[before] = PyList.fromList(rest);
        return result;
    }

    private static PyException tooFew(int expected, int actual) {
        return Py.ValueError(String.format(
                "not enough values to unpack (expected at least %d, got %d)", expected, actual));
    }

    /** Consume now, before the next display expression is evaluated. */
    public static void extendList(PyList result, PyObject iterable) {
        for (PyObject value : iterable.asIterable()) {
            result.append(value);
        }
    }

    /** Insert during iteration so hashing failures stop further consumption. */
    public static void extendSet(PySet result, PyObject iterable) {
        for (PyObject value : iterable.asIterable()) {
            result.set_add(value);
        }
    }

    public static void addSet(PySet result, PyObject value) {
        result.set_add(value);
    }

    /** Merge mappings only; unlike dict.update, an iterable of pairs is not accepted. */
    public static void mergeMapping(PyDictionary result, PyObject mapping) {
        // Python dict subclasses retain the fast path unless they override iteration.
        if (mapping instanceof PyDictionary
                && mapping.getType().lookup("__iter__") == PyDictionary.TYPE.lookup("__iter__")) {
            result.getMap().putAll(((PyDictionary)mapping).getMap());
            return;
        }
        PyObject keysMethod = mapping.__findattr__("keys");
        if (keysMethod == null) {
            throw Py.TypeError(String.format("'%s' object is not a mapping",
                    mapping.getType().fastGetName()));
        }
        PyObject keys = keysMethod.__call__();
        // Exhaust a key iterator before requesting any values, but keep an exact
        // list live just as PyMapping_Keys does. Exceptions from user code propagate.
        if (keys.getType() != PyList.TYPE) {
            keys = new PyList(keys);
        }
        for (PyObject key : keys.asIterable()) {
            result.__setitem__(key, mapping.__getitem__(key));
        }
    }
}
