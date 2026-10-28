// AST node corresponding to NamedExpr(expr target, expr value) in Python.asdl.
package org.python.antlr.ast;

import org.antlr.runtime.Token;
import org.python.antlr.PythonTree;
import org.python.antlr.adapter.AstAdapters;
import org.python.antlr.base.expr;
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

@ExposedType(name = "_ast.NamedExpr", base = expr.class)
public class NamedExpr extends expr {
    public static final PyType TYPE = PyType.fromClass(NamedExpr.class);
    private expr target;
    private expr value;
    public PyObject __dict__;
    private int lineno = -1;
    private int col_offset = -1;
    private static final PyString[] fields = {new PyString("target"), new PyString("value")};
    private static final PyString[] attributes = {new PyString("lineno"), new PyString("col_offset")};

    public NamedExpr() { this(TYPE); }
    public NamedExpr(PyType subtype) { super(subtype); }
    public NamedExpr(PyObject target, PyObject value) {
        setTarget(target);
        setValue(value);
    }
    public NamedExpr(Token token, expr target, expr value) {
        super(token);
        this.target = target;
        this.value = value;
        addChild(target);
        addChild(value);
    }
    public NamedExpr(Integer ttype, Token token, expr target, expr value) {
        super(ttype, token);
        this.target = target;
        this.value = value;
        addChild(target);
        addChild(value);
    }
    public NamedExpr(PythonTree tree, expr target, expr value) {
        super(tree);
        this.target = target;
        this.value = value;
        addChild(target);
        addChild(value);
    }

    @ExposedNew
    @ExposedMethod
    public void NamedExpr___init__(PyObject[] args, String[] keywords) {
        ArgParser ap = new ArgParser("NamedExpr", args, keywords,
                new String[] {"target", "value", "lineno", "col_offset"}, 2, true);
        setTarget(ap.getPyObject(0, Py.None));
        setValue(ap.getPyObject(1, Py.None));
        int line = ap.getInt(2, -1);
        if (line != -1) setLineno(line);
        int column = ap.getInt(3, -1);
        if (column != -1) setCol_offset(column);
    }

    public expr getInternalTarget() { return target; }
    public expr getInternalValue() { return value; }
    @ExposedGet(name = "target")
    public PyObject getTarget() { return target; }
    @ExposedSet(name = "target")
    public void setTarget(PyObject target) { this.target = AstAdapters.py2expr(target); }
    @ExposedGet(name = "value")
    public PyObject getValue() { return value; }
    @ExposedSet(name = "value")
    public void setValue(PyObject value) { this.value = AstAdapters.py2expr(value); }
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
    public String toString() { return "NamedExpr"; }
    @Override
    public String toStringTree() {
        return "NamedExpr(target=" + dumpThis(target) + ",value=" + dumpThis(value) + ",)";
    }
    @Override
    public <R> R accept(VisitorIF<R> visitor) throws Exception {
        return visitor.visitNamedExpr(this);
    }
    @Override
    public void traverse(VisitorIF<?> visitor) throws Exception {
        if (target != null) target.accept(visitor);
        if (value != null) value.accept(visitor);
    }
    @Override
    public int traverse(Visitproc visit, Object arg) {
        int result = super.traverse(visit, arg);
        if (result != 0) return result;
        if (target != null) {
            result = visit.visit(target, arg);
            if (result != 0) return result;
        }
        if (value != null) {
            result = visit.visit(value, arg);
            if (result != 0) return result;
        }
        return __dict__ == null ? 0 : visit.visit(__dict__, arg);
    }
    @Override
    public boolean refersDirectlyTo(PyObject object) {
        return object != null && (object == target || object == value || object == __dict__
                || super.refersDirectlyTo(object));
    }
}
