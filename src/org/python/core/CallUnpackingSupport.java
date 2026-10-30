package org.python.core;

import java.util.LinkedHashMap;
import java.util.Map;

/** A per-call accumulator saved in a typed JVM local across generator suspension. */
public final class CallUnpackingSupport implements Traverseproc {
    private final PyObject callable;
    private final PyList positional = new PyList();
    private final Map<PyObject, PyObject> keywords = new LinkedHashMap<>();
    private PyObject deferredStar;

    public CallUnpackingSupport(PyObject callable) {
        this.callable = callable;
    }

    private String callName() {
        if (callable instanceof PyFunction) {
            return ((PyFunction)callable).__name__ + "() ";
        }
        if (callable instanceof PyBuiltinCallable) {
            return ((PyBuiltinCallable)callable).fastGetName() + "() ";
        }
        return callable.getType().fastGetName() + " object ";
    }

    public void add(PyObject value) {
        positional.append(value);
    }

    public void extend(PyObject iterable) {
        // Do not use Py.iter's error wrapper: a user __iter__ may raise TypeError.
        PyObject iterator = iterable.__iter__();
        for (PyObject value; (value = iterator.__iternext__()) != null;) {
            positional.append(value);
        }
    }

    /** A sole *operand is consumed at invocation, after keyword expressions/merges. */
    public void defer(PyObject iterable) {
        deferredStar = iterable;
    }

    private void checkDuplicate(PyObject key) {
        // HashMap may skip hashing on an empty table. Python must still reject
        // an unhashable first key before the mapping's __getitem__ is invoked.
        if (keywords.isEmpty()) {
            key.hashCode();
        }
        if (keywords.containsKey(key)) {
            throw Py.TypeError(callName() + "got multiple values for keyword argument '"
                    + key + "'");
        }
    }

    /** Consecutive named values have already been evaluated before this group is merged. */
    public void addKeywords(PyObject[] values, String[] names) {
        if (values.length != names.length) {
            throw new IllegalArgumentException("Keyword names and values must have equal length");
        }
        for (int i = 0; i < names.length; i++) {
            PyObject key = Py.newString(names[i]);
            checkDuplicate(key);
            keywords.put(key, values[i]);
        }
    }

    public void merge(PyObject mapping) {
        if (mapping instanceof PyDictionary
                && mapping.getType().lookup("__iter__") == PyDictionary.TYPE.lookup("__iter__")) {
            for (Map.Entry<PyObject, PyObject> entry : ((PyDictionary)mapping).getMap().entrySet()) {
                checkDuplicate(entry.getKey());
                keywords.put(entry.getKey(), entry.getValue());
            }
            return;
        }
        PyObject method = mapping.__findattr__("keys");
        if (method == null) {
            throw Py.TypeError(callName() + "argument after ** must be a mapping, not "
                    + mapping.getType().fastGetName());
        }
        PyObject keys = method.__call__();
        if (keys.getType() != PyList.TYPE) {
            keys = new PyList(keys);
        }
        for (PyObject key : keys.asIterable()) {
            // Detect duplicates before asking the mapping for the conflicting value.
            checkDuplicate(key);
            keywords.put(key, mapping.__getitem__(key));
        }
    }

    public PyObject keywordDictionary() {
        PyDictionary result = new PyDictionary();
        for (Map.Entry<PyObject, PyObject> entry : keywords.entrySet()) {
            if (!(entry.getKey() instanceof PyString)) {
                throw Py.TypeError("keywords must be strings");
            }
            result.__setitem__(entry.getKey(), entry.getValue());
        }
        return result;
    }

    public PyObject call(ThreadState state) {
        if (deferredStar != null) {
            extend(deferredStar);
            deferredStar = null;
        }
        PyObject[] args = new PyObject[positional.__len__() + keywords.size()];
        PyObject[] prefix = positional.getArray();
        System.arraycopy(prefix, 0, args, 0, prefix.length);
        String[] names = new String[keywords.size()];
        int i = 0;
        for (Map.Entry<PyObject, PyObject> entry : keywords.entrySet()) {
            // Like CALL_FUNCTION_EX, reject non-string keys after all merges.
            if (!(entry.getKey() instanceof PyString)) {
                throw Py.TypeError(callName() + "keywords must be strings");
            }
            names[i] = ((PyString)entry.getKey()).internedString();
            args[prefix.length + i++] = entry.getValue();
        }
        return callable.__call__(state, args, names);
    }

    @Override
    public int traverse(Visitproc visit, Object arg) {
        int result = visit.visit(callable, arg);
        if (result == 0) result = visit.visit(positional, arg);
        if (result == 0 && deferredStar != null) result = visit.visit(deferredStar, arg);
        if (result != 0) return result;
        for (Map.Entry<PyObject, PyObject> entry : keywords.entrySet()) {
            result = visit.visit(entry.getKey(), arg);
            if (result == 0) result = visit.visit(entry.getValue(), arg);
            if (result != 0) return result;
        }
        return 0;
    }

    @Override
    public boolean refersDirectlyTo(PyObject object) {
        if (object == null) return false;
        if (object == callable || object == positional || object == deferredStar) return true;
        for (Map.Entry<PyObject, PyObject> entry : keywords.entrySet()) {
            if (object == entry.getKey() || object == entry.getValue()) return true;
        }
        return false;
    }
}
