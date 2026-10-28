/* Copyright (c) Jython Developers */
package org.python.core;

import org.python.core.finalization.FinalizableBuiltin;
import org.python.core.finalization.FinalizeTrigger;
import org.python.expose.ExposedGet;
import org.python.expose.ExposedMethod;
import org.python.expose.ExposedType;

@ExposedType(name = "generator", base = PyObject.class, isBaseType = false)
public class PyGenerator extends PyIterator implements FinalizableBuiltin {

    public static final PyType TYPE = PyType.fromClass(PyGenerator.class);

    @ExposedGet
    protected PyFrame gi_frame;

    @ExposedGet
    protected PyCode gi_code = null;

    @ExposedGet
    protected boolean gi_running;

    private PyObject closure;

    public PyGenerator(PyFrame frame, PyObject closure) {
        super(TYPE);
        gi_frame = frame;
        if (gi_frame != null) {
            gi_code = gi_frame.f_code;
        }
        this.closure = closure;
        FinalizeTrigger.ensureFinalizer(this);
    }

    @ExposedGet(name = "__name__")
    public String getName() {
        return gi_code.co_name;
    }

    @ExposedGet(name = "gi_yieldfrom")
    public PyObject getYieldFrom() {
        return gi_frame == null || gi_running || gi_frame.f_yieldfrom == null
                ? Py.None : gi_frame.f_yieldfrom;
    }

    private void checkRunning() {
        if (gi_running) throw Py.ValueError("generator already executing");
    }

    private void clearFrame() {
        if (gi_frame != null) {
            gi_frame.f_yieldfrom = null;
            gi_frame.f_savedlocals = null;
            gi_frame.setGeneratorInput(Py.None);
        }
        gi_frame = null;
    }

    public PyObject send(PyObject value) {
        return generator_send(value);
    }

    @ExposedMethod
    final PyObject generator_send(PyObject value) {
        checkRunning();
        if (gi_frame == null) {
            throw new PyException(Py.StopIteration);
        }
        if (gi_frame.f_lasti == 0 && value != Py.None) {
            throw Py.TypeError("can't send non-None value to a just-started generator");
        }
        gi_frame.setGeneratorInput(value);
        return next();
    }

    public PyObject throw$(PyObject type, PyObject value, PyObject tb) {
        return generator_throw$(type, value, tb);
    }

    @ExposedMethod(names="throw", defaults={"null", "null"})
    final PyObject generator_throw$(PyObject type, PyObject value, PyObject tb) {
        checkRunning();
        PyObject[] arguments = tb != null ? new PyObject[] {type, value, tb}
                : value != null ? new PyObject[] {type, value} : new PyObject[] {type};
        if (tb == Py.None) {
            tb = null;
        } else if (tb != null && !(tb instanceof PyTraceback)) {
            throw Py.TypeError("throw() third argument must be a traceback object");
        }
        PyObject exceptionType = type instanceof PyBaseException ? type.getType() : type;
        boolean closing = exceptionType instanceof PyType
                && ((PyType)exceptionType).isSubType((PyType)Py.GeneratorExit);
        if (gi_frame != null && gi_frame.f_yieldfrom != null && !closing) {
            // Do not construct the exception before forwarding. Each delegating
            // level must preserve raw arguments without repeating __init__.
            PyObject method;
            gi_running = true;
            try {
                method = YieldFromSupport.optional(gi_frame.f_yieldfrom, "throw");
            } finally {
                gi_running = false;
            }
            YieldFromSupport.InjectedException exception = method == null
                    ? new YieldFromSupport.InjectedException(Py.makeException(type, value, tb), arguments)
                    : new YieldFromSupport.InjectedException(arguments, method);
            exception.prepared = true;
            return raiseException(exception);
        }
        return raiseException(Py.makeException(type, value, tb));
    }

    public PyObject close() {
        return generator_close();
    }

    @ExposedMethod
    final PyObject generator_close() {
        checkRunning();
        try {
            raiseException(Py.makeException(Py.GeneratorExit));
            throw Py.RuntimeError("generator ignored GeneratorExit");
        } catch (PyException e) {
            if (e.match(Py.StopIteration)) return YieldFromSupport.stopValue(e);
            if (!e.match(Py.GeneratorExit)) throw e;
        }
        return Py.None;
    }

    @Override
    public PyObject next() {
        return generator_next();
    }

    @ExposedMethod(doc="x.next() -> the next value, or raise StopIteration")
    final PyObject generator_next() {
        PyObject value = __iternext__();
        if (value == null && stopException == null) throw new PyException(Py.StopIteration);
        return doNext(value);
    }

    @ExposedMethod(names = "__next__")
    final PyObject generator___next__() {
        return generator_next();
    }

    @Override
    public PyObject __iter__() {
        return generator___iter__();
    }

    @ExposedMethod
    final PyObject generator___iter__() {
        return this;
    }

    private PyObject raiseException(PyException ex) {
        checkRunning();
        if (gi_frame == null || gi_frame.f_lasti == 0) {
            clearFrame();
            throw ex;
        }
        gi_frame.setGeneratorInput(ex);
        return next();
    }
    
    @Override
    public void __del_builtin__() {
        if (gi_frame == null || gi_frame.f_lasti == -1) {
            return;
        }
        try {
            close();
        } catch (PyException pye) {
            // PEP 342 specifies that if an exception is raised by close,
            // we output to stderr and then forget about it;
            String className =  PyException.exceptionClassName(pye.type);
            int lastDot = className.lastIndexOf('.');
            if (lastDot != -1) {
                className = className.substring(lastDot + 1);
            }
            String msg = String.format("Exception %s: %s in %s", className, pye.value.__repr__(),
                                       __repr__());
            Py.println(Py.getSystemState().stderr, Py.newString(msg));
        } catch (Throwable t) {
            // but we currently ignore any Java exception completely. perhaps we
            // can also output something meaningful too?
        }
    }

    @Override
    public PyObject __iternext__() {
        return __iternext__(Py.getThreadState());
    }

    public PyObject __iternext__(ThreadState state) {
        if (gi_running) {
            throw Py.ValueError("generator already executing");
        }
        stopException = null;
        if (gi_frame == null) {
            return null;
        }

        if (gi_frame.f_lasti == -1) {
            clearFrame();
            return null;
        }
        gi_running = true;
        PyObject result = null;
        try {
            result = gi_frame.f_code.call(state, gi_frame, closure);
        } catch (PyException pye) {
            clearFrame();
            if (!pye.match(Py.StopIteration)) throw pye;
            // PEP 479 applies only to exceptions escaping an executing body.
            // Normal returns below, and throw into an unstarted/closed generator,
            // must keep their StopIteration protocol. Preserve the original
            // instance and traceback as both cause and context of the wrapper.
            PyException error = Py.RuntimeError("generator raised StopIteration");
            error.normalize();
            PyBaseException value = (PyBaseException)error.value;
            value.setCause(pye.value);
            value.setContext(pye.value);
            throw error;
        } finally {
            gi_running = false;
        }
        if (gi_frame.f_lasti == -1) {
            clearFrame();
            if (result != Py.None) stopException = Py.StopIterationValue(result);
            return null;
        }
        return result;
    }

    @Override
    public String toString() {
        return generator_toString();
    }

    @ExposedMethod(names = "__repr__")
    final String generator_toString() {
        return String.format("<generator object %s at %s>", getName(), Py.idstr(this));
    }


    /* Traverseproc implementation */
    @Override
    public int traverse(Visitproc visit, Object arg) {
        int retValue = super.traverse(visit, arg);
        if (retValue != 0) {
            return retValue;
        }
        if (gi_frame != null) {
            retValue = visit.visit(gi_frame, arg);
            if (retValue != 0) {
                return retValue;
            }
        }
        if (gi_code != null) {
            retValue = visit.visit(gi_code, arg);
            if (retValue != 0) {
                return retValue;
            }
        }
        return closure == null ? 0 : visit.visit(closure, arg);
    }

    @Override
    public boolean refersDirectlyTo(PyObject ob) {
        return ob != null && (ob == gi_frame || ob == gi_code
            || ob == closure || super.refersDirectlyTo(ob));
    }
}
