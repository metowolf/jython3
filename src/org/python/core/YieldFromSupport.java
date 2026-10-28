package org.python.core;

/** State held in typed JVM locals while a yield-from expression is suspended. */
public final class YieldFromSupport implements Traverseproc {
    private PyObject iterator;
    private PyObject result = Py.None;

    private YieldFromSupport(PyObject iterator) {
        this.iterator = iterator;
    }

    public static YieldFromSupport start(PyObject iterable) {
        return new YieldFromSupport(iterable.__iter__());
    }

    /** Null means completion, while Py.None is an ordinary yielded value. */
    public PyObject advance(PyFrame frame, Object input) {
        frame.f_yieldfrom = null;
        try {
            boolean forwarding = input instanceof InjectedException
                    && ((InjectedException)input).method != null;
            if (!forwarding && input instanceof PyException
                    && ((PyException)input).match(Py.GeneratorExit)) {
                PyObject close = null;
                try {
                    close = optional(iterator, "close");
                } catch (PyException exception) {
                    // CPython reports failed close lookup as unraisable, then
                    // still injects GeneratorExit into the delegating generator.
                    Py.writeUnraisable(exception, iterator);
                }
                if (close != null) {
                    try {
                        close.__call__(Py.getThreadState());
                    } catch (PyException exception) {
                        if (!exception.match(Py.StopIteration)) throw exception;
                        result = stopValue(exception);
                        iterator = null;
                        return null;
                    }
                }
                throw ((PyException)input).chainContext();
            }
            PyObject throwMethod = null;
            if (input instanceof PyException) {
                PyException exception = (PyException)input;
                throwMethod = exception instanceof InjectedException
                        && ((InjectedException)exception).prepared
                        ? ((InjectedException)exception).method : optional(iterator, "throw");
            }
            PyObject value;
            try {
                if (input instanceof PyException) {
                    PyException exception = (PyException)input;
                    // Match CPython 3.15 CLEANUP_THROW: even an injected
                    // StopIteration completes delegation if throw is absent.
                    if (throwMethod == null) throw exception.chainContext();
                    PyObject[] args;
                    if (exception instanceof InjectedException) {
                        args = ((InjectedException)exception).arguments;
                    } else {
                        exception.normalize();
                        args = new PyObject[] {exception.type, exception.value,
                                exception.traceback == null ? Py.None : exception.traceback};
                    }
                    value = throwMethod.__call__(Py.getThreadState(), args);
                } else if (input == Py.None) {
                    value = next(iterator);
                } else {
                    value = iterator.__getattr__("send").__call__(Py.getThreadState(), (PyObject)input);
                }
            } catch (PyException exception) {
                if (!exception.match(Py.StopIteration)) throw exception;
                result = stopValue(exception);
                iterator = null;
                return null;
            }
            frame.f_yieldfrom = iterator;
            return value;
        } catch (RuntimeException exception) {
            iterator = null;
            throw exception;
        }
    }

    static PyObject optional(PyObject object, String name) {
        try {
            return object.__getattr__(name);
        } catch (PyException exception) {
            if (exception.match(Py.AttributeError)) return null;
            throw exception;
        }
    }

    private static PyObject next(PyObject iterator) {
        // Python-defined next slots must be invoked directly: legacy __iternext__
        // implementations swallow StopIteration and would lose its return value.
        PyObject method = iterator.getType().lookup("__next__");
        if (method == null && !(iterator instanceof PyIterator)) {
            method = iterator.getType().lookup("next");
        }
        if (method != null) {
            return method.__get__(iterator, iterator.getType()).__call__(Py.getThreadState());
        }
        if (iterator instanceof PyInstance) {
            return iterator.__getattr__("next").__call__(Py.getThreadState());
        }
        PyObject value = iterator.__iternext__();
        if (value != null) return value;
        if (iterator instanceof PyIterator) {
            PyIterator nativeIterator = (PyIterator)iterator;
            if (nativeIterator.stopException != null) {
                PyException stopped = nativeIterator.stopException;
                nativeIterator.stopException = null;
                throw stopped;
            }
        }
        throw new PyException(Py.StopIteration);
    }

    public static PyObject stopValue(PyException exception) {
        exception.normalize();
        return ((PyBaseException)exception.value).stopIterationValue;
    }

    public PyObject result() {
        PyObject value = result;
        result = Py.None;
        return value;
    }

    /** Keep the caller's original one/two/three argument throw signature intact. */
    static final class InjectedException extends PyException {
        final PyObject[] arguments;
        boolean prepared;
        PyObject method;

        InjectedException(PyObject[] arguments, PyObject method) {
            super(Py.None, Py.None);
            this.arguments = arguments;
            this.method = method;
        }

        InjectedException(PyException exception, PyObject[] arguments) {
            super(exception.type, exception.value, exception.traceback);
            this.arguments = arguments;
        }

        @Override
        public int traverse(Visitproc visit, Object arg) {
            int result = super.traverse(visit, arg);
            if (result != 0) return result;
            for (PyObject object : arguments) {
                result = visit.visit(object, arg);
                if (result != 0) return result;
            }
            return method == null ? 0 : visit.visit(method, arg);
        }

        @Override
        public boolean refersDirectlyTo(PyObject object) {
            if (object == null) return false;
            for (PyObject argument : arguments) if (argument == object) return true;
            return object == method || super.refersDirectlyTo(object);
        }
    }

    @Override
    public int traverse(Visitproc visit, Object arg) {
        if (iterator != null) {
            int value = visit.visit(iterator, arg);
            if (value != 0) return value;
        }
        return result == Py.None ? 0 : visit.visit(result, arg);
    }

    @Override
    public boolean refersDirectlyTo(PyObject object) {
        return object != null && (object == iterator || object == result);
    }
}
