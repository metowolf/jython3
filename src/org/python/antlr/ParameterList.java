package org.python.antlr;

import java.util.ArrayList;
import java.util.List;

import org.antlr.runtime.Token;
import org.python.antlr.ast.Name;
import org.python.antlr.ast.arguments;
import org.python.antlr.ast.expr_contextType;
import org.python.antlr.ast.keyword;
import org.python.antlr.base.expr;

/** Collect and validate parameters shared by function and lambda grammars. */
public final class ParameterList {
    private final Token token;
    private final List<expr> positional = new ArrayList<expr>();
    private final List<expr> posonly = new ArrayList<expr>();
    private final List<expr> defaults = new ArrayList<expr>();
    private final List<expr> kwonly = new ArrayList<expr>();
    private final List<expr> kwDefaults = new ArrayList<expr>();
    private final List<keyword> annotations = new ArrayList<keyword>();
    private Name vararg;
    private Name kwarg;
    private boolean star;
    private boolean slash;

    public ParameterList(Token token) {
        this.token = token;
    }

    public void add(expr parameter, expr annotation, expr value) {
        if (kwarg != null) {
            throw new ParseException("arguments cannot follow **kwargs", parameter);
        }
        if (star) {
            if (!(parameter instanceof Name)) {
                throw new ParseException("keyword-only argument must be a name", parameter);
            }
            kwonly.add(parameter);
            // Null denotes a required keyword-only argument, not a default of None.
            kwDefaults.add(value);
        } else {
            if (value != null) {
                defaults.add(value);
            } else if (!defaults.isEmpty()) {
                throw new ParseException("non-default argument follows default argument", parameter);
            }
            positional.add(parameter);
        }
        annotate(parameter, annotation);
    }

    public void addStar(Token marker, Token name, expr annotation) {
        if (star || kwarg != null) {
            throw new ParseException("* argument may appear only once, before **kwargs",
                    new PythonTree(marker));
        }
        star = true;
        if (name != null) {
            vararg = parameterName(name);
            annotate(vararg, annotation);
        }
    }

    public void addKwarg(Token marker, Token name, expr annotation) {
        if (kwarg != null) {
            throw new ParseException("** argument may appear only once", new PythonTree(marker));
        }
        kwarg = parameterName(name);
        annotate(kwarg, annotation);
    }

    public void positionalOnly(Token marker) {
        if (slash || star || kwarg != null || positional.isEmpty()) {
            throw new ParseException("/ must follow positional parameters and precede *",
                    new PythonTree(marker));
        }
        slash = true;
        posonly.addAll(positional);
        positional.clear();
    }

    private Name parameterName(Token name) {
        Name node = new Name(name, name.getText(), expr_contextType.Param);
        if ("None".equals(name.getText()) || "__debug__".equals(name.getText())) {
            throw new ParseException("cannot assign to " + name.getText(), node);
        }
        return node;
    }

    private void annotate(expr parameter, expr annotation) {
        if (annotation != null) {
            if (!(parameter instanceof Name)) {
                throw new ParseException("annotated parameter must be a name", parameter);
            }
            annotations.add(new keyword(parameter, ((Name) parameter).getInternalId(), annotation));
        }
    }

    public arguments finish() {
        if (star && vararg == null && kwonly.isEmpty()) {
            throw new ParseException("named arguments must follow bare *", new PythonTree(token));
        }
        arguments result = new arguments(token, positional, vararg, kwarg, defaults);
        result.getInternalPosonlyargs().addAll(posonly);
        result.getInternalKwonlyargs().addAll(kwonly);
        result.getInternalKw_defaults().addAll(kwDefaults);
        result.getInternalAnnotations().addAll(annotations);
        for (expr node : posonly) {
            result.addChild(node);
        }
        for (expr node : kwonly) {
            result.addChild(node);
        }
        for (expr node : kwDefaults) {
            result.addChild(node);
        }
        for (keyword node : annotations) {
            result.addChild(node);
        }
        return result;
    }
}
