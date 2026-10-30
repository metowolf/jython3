package org.python.compiler;

import org.python.antlr.PythonTree;
import org.python.antlr.ParseException;
import org.python.antlr.ast.*;
import org.python.antlr.base.expr;
import org.python.core.Py;
import org.python.core.PyObject;

/** Stringization for PEP 563, independent of runtime name resolution. */
final class AnnotationText {
    private AnnotationText() {}

    static expr literal(expr value) {
        String text;
        try {
            text = render(value);
        } catch (ParseException error) {
            // Nested expressions may not carry their own retained source span.
            // Fall back to the complete annotation, never evaluate its contents.
            if (value.annotationSource == null) throw error;
            text = value.annotationSource;
        }
        return new Str(value, Py.newUnicode(text));
    }

    private static String join(java.util.List<? extends PythonTree> values) {
        StringBuilder text = new StringBuilder();
        for (PythonTree value : values) {
            if (text.length() != 0) text.append(", ");
            text.append(render(value));
        }
        return text.toString();
    }

    static String render(PythonTree value) {
        if (value instanceof Name) return ((Name)value).getInternalId();
        if (value instanceof Attribute) {
            Attribute a = (Attribute)value;
            return render(a.getInternalValue()) + "." + a.getInternalAttr();
        }
        if (value instanceof Subscript) {
            Subscript s = (Subscript)value;
            return render(s.getInternalValue()) + "[" + render(s.getInternalSlice()) + "]";
        }
        if (value instanceof Index) {
            expr e = ((Index)value).getInternalValue();
            return e instanceof Tuple ? tuple((Tuple)e) : render(e);
        }
        if (value instanceof ExtSlice) return join(((ExtSlice)value).getInternalDims());
        if (value instanceof Ellipsis) return "...";
        if (value instanceof Str) {
            String r = ((PyObject)((Str)value).getInternalS()).__repr__().toString();
            return r.startsWith("u'") || r.startsWith("u\"") ? r.substring(1) : r;
        }
        if (value instanceof Num) {
            String r = ((PyObject)((Num)value).getInternalN()).__repr__().toString();
            return r.endsWith("L") ? r.substring(0, r.length() - 1) : r;
        }
        if (value instanceof Tuple) return "(" + tuple((Tuple)value) + ")";
        if (value instanceof org.python.antlr.ast.List) {
            return "[" + join(((org.python.antlr.ast.List)value).getInternalElts()) + "]";
        }
        if (value instanceof BinOp && ((BinOp)value).getInternalOp() == operatorType.BitOr) {
            BinOp b = (BinOp)value;
            return render(b.getInternalLeft()) + " | " + render(b.getInternalRight());
        }
        // The parser retains the exact expression for less common annotations.
        // Wrapping makes multiline expressions and comments safe to eval later.
        if (value.annotationSource != null) return value.annotationSource;
        throw new ParseException("cannot stringify this annotation AST", value);
    }

    private static String tuple(Tuple value) {
        return join(value.getInternalElts()) + (value.getInternalElts().size() == 1 ? "," : "");
    }
}
