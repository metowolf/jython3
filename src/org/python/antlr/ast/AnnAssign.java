// AST node corresponding to AnnAssign in Python.asdl.
package org.python.antlr.ast;

import org.antlr.runtime.Token;
import org.python.antlr.PythonTree;
import org.python.antlr.adapter.AstAdapters;
import org.python.antlr.base.expr;
import org.python.antlr.base.stmt;
import org.python.core.ArgParser;
import org.python.core.Py;
import org.python.core.PyObject;
import org.python.core.PyString;
import org.python.core.PyStringMap;
import org.python.core.PyType;
import org.python.core.Visitproc;
import org.python.expose.ExposedGet;
import org.python.expose.ExposedMethod;
import org.python.expose.ExposedNew;
import org.python.expose.ExposedSet;
import org.python.expose.ExposedType;

@ExposedType(name = "_ast.AnnAssign", base = stmt.class)
public class AnnAssign extends stmt {
    public static final PyType TYPE = PyType.fromClass(AnnAssign.class);
    private expr target, annotation, value;
    private int simple;
    public PyObject __dict__;
    private int lineno = -1, col_offset = -1;
    private static final PyString[] fields = {new PyString("target"), new PyString("annotation"),
            new PyString("value"), new PyString("simple")};
    private static final PyString[] attributes = {new PyString("lineno"), new PyString("col_offset")};

    public AnnAssign() { this(TYPE); }
    public AnnAssign(PyType subtype) { super(subtype); }
    public AnnAssign(Token token, expr target, expr annotation, expr value, Integer simple) {
        super(token);
        this.target = target;
        this.annotation = annotation;
        this.value = value;
        this.simple = simple;
        addChild(target);
        addChild(annotation);
        addChild(value);
    }

    @ExposedNew
    @ExposedMethod
    public void AnnAssign___init__(PyObject[] args, String[] keywords) {
        ArgParser ap = new ArgParser("AnnAssign", args, keywords,
                new String[] {"target", "annotation", "value", "simple", "lineno", "col_offset"}, 4, true);
        setTarget(ap.getPyObject(0, Py.None));
        setAnnotation(ap.getPyObject(1, Py.None));
        setValue(ap.getPyObject(2, Py.None));
        simple = ap.getInt(3, 0);
        lineno = ap.getInt(4, -1);
        col_offset = ap.getInt(5, -1);
    }

    public expr getInternalTarget() { return target; }
    public expr getInternalAnnotation() { return annotation; }
    public expr getInternalValue() { return value; }
    public int getInternalSimple() { return simple; }
    @ExposedGet(name = "target")
    public PyObject getTarget() { return target == null ? Py.None : target; }
    @ExposedSet(name = "target")
    public void setTarget(PyObject target) { this.target = AstAdapters.py2expr(target); }
    @ExposedGet(name = "annotation")
    public PyObject getAnnotation() { return annotation == null ? Py.None : annotation; }
    @ExposedSet(name = "annotation")
    public void setAnnotation(PyObject annotation) { this.annotation = AstAdapters.py2expr(annotation); }
    @ExposedGet(name = "value")
    public PyObject getValue() { return value == null ? Py.None : value; }
    @ExposedSet(name = "value")
    public void setValue(PyObject value) { this.value = AstAdapters.py2expr(value); }
    @ExposedGet(name = "simple")
    public int getSimple() { return simple; }
    @ExposedSet(name = "simple")
    public void setSimple(int simple) { this.simple = simple; }
    @ExposedGet(name = "_fields")
    public PyString[] get_fields() { return fields; }
    @ExposedGet(name = "_attributes")
    public PyString[] get_attributes() { return attributes; }
    @ExposedGet(name = "lineno")
    public int getLineno() { return lineno == -1 ? getLine() : lineno; }
    @ExposedSet(name = "lineno")
    public void setLineno(int line) { lineno = line; }
    @ExposedGet(name = "col_offset")
    public int getCol_offset() { return col_offset == -1 ? getCharPositionInLine() : col_offset; }
    @ExposedSet(name = "col_offset")
    public void setCol_offset(int column) { col_offset = column; }
    @Override
    public PyObject fastGetDict() {
        if (__dict__ == null) __dict__ = new PyStringMap();
        return __dict__;
    }
    @ExposedGet(name = "__dict__")
    public PyObject getDict() { return fastGetDict(); }
    @Override
    @ExposedGet(name = "repr")
    public String toString() { return "AnnAssign"; }
    @Override
    public String toStringTree() {
        return "AnnAssign(target=" + dumpThis(target) + ",annotation=" + dumpThis(annotation)
                + ",value=" + dumpThis(value) + ",simple=" + simple + ",)";
    }
    @Override
    public <R> R accept(VisitorIF<R> visitor) throws Exception { return visitor.visitAnnAssign(this); }
    @Override
    public void traverse(VisitorIF<?> visitor) throws Exception {
        if (target != null) target.accept(visitor);
        if (annotation != null) annotation.accept(visitor);
        if (value != null) value.accept(visitor);
    }
    @Override
    public int traverse(Visitproc visit, Object arg) {
        int result = super.traverse(visit, arg);
        if (result != 0) return result;
        for (PyObject child : new PyObject[] {target, annotation, value, __dict__}) {
            if (child != null && (result = visit.visit(child, arg)) != 0) return result;
        }
        return 0;
    }
    @Override
    public boolean refersDirectlyTo(PyObject ob) {
        return ob != null && (ob == target || ob == annotation || ob == value || ob == __dict__
                || super.refersDirectlyTo(ob));
    }
}
