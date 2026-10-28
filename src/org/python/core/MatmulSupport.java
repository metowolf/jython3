package org.python.core;

/** Native PEP 465 dispatch, independent of Python 2 arithmetic/coercion rules. */
public final class MatmulSupport {
    private MatmulSupport() {}

    public static PyObject matmul(PyObject left, PyObject right) {
        return binary(left, right, "@");
    }

    public static PyObject imatmul(PyObject left, PyObject right) {
        PyObject owner = owner(left);
        PyObject result = call(lookup(owner, "__imatmul__"), owner, left, right);
        return result != Py.NotImplemented ? result : binary(left, right, "@=");
    }

    private static PyObject binary(PyObject left, PyObject right, String symbol) {
        PyObject leftType = owner(left);
        PyObject rightType = owner(right);
        boolean different = leftType != rightType;
        boolean rightFirst = different && isSubtype(rightType, leftType)
                && reflectedIsOverloaded(leftType, rightType);
        PyObject result;
        if (rightFirst) {
            PyObject reflected = lookup(rightType, "__rmatmul__");
            result = call(reflected, rightType, right, left);
            if (result != Py.NotImplemented) {
                return result;
            }
        }
        result = call(lookup(leftType, "__matmul__"), leftType, left, right);
        if (result != Py.NotImplemented) {
            return result;
        }
        // Same-type operands never retry the reflected method. A prioritized
        // right method returning NotImplemented must not be called twice.
        if (different && !rightFirst) {
            result = call(lookup(rightType, "__rmatmul__"), rightType, right, left);
            if (result != Py.NotImplemented) {
                return result;
            }
        }
        throw Py.TypeError(String.format("unsupported operand type(s) for %s: '%s' and '%s'",
                symbol, typeName(leftType), typeName(rightType)));
    }

    private static PyObject call(PyObject method, PyObject owner, PyObject self, PyObject other) {
        if (method == null) {
            return Py.NotImplemented;
        }
        // Special methods live on the class, not in the instance dictionary.
        // Bind descriptors normally, including reflected Java methods.
        return method.__get__(self, owner).__call__(Py.getThreadState(), other);
    }

    private static boolean reflectedIsOverloaded(PyObject leftType, PyObject rightType) {
        // Match typeobject.c's method_is_overloaded: class-level descriptor
        // binding and rich comparison matter (not just raw dictionary identity).
        PyObject right = implementation(rightType.__findattr__("__rmatmul__"));
        if (right == null) {
            return false;
        }
        PyObject left = implementation(leftType.__findattr__("__rmatmul__"));
        return left == null || left != right && left._ne(right).__nonzero__();
    }

    private static PyObject implementation(PyObject method) {
        // Assigning Base.__rmatmul__ on this legacy runtime stores an unbound
        // PyMethod, whereas Python 3 stores the function itself.
        if (method instanceof PyMethod && ((PyMethod)method).__self__ == null) {
            return ((PyMethod)method).__func__;
        }
        return method;
    }

    private static PyObject owner(PyObject value) {
        return value instanceof PyInstance ? ((PyInstance)value).instclass : value.getType();
    }

    private static PyObject lookup(PyObject owner, String name) {
        return owner instanceof PyClass ? ((PyClass)owner).lookup(name) : ((PyType)owner).lookup(name);
    }

    private static boolean isSubtype(PyObject child, PyObject parent) {
        if (child instanceof PyType && parent instanceof PyType) {
            return ((PyType)child).isSubType((PyType)parent);
        }
        return child instanceof PyClass && parent instanceof PyClass
                && ((PyClass)child).isSubClass((PyClass)parent);
    }

    private static String typeName(PyObject owner) {
        return owner instanceof PyClass ? ((PyClass)owner).__name__ : ((PyType)owner).fastGetName();
    }
}
