// Copyright (c) Corporation for National Research Initiatives

package org.python.compiler;

import java.util.ArrayList;
import java.util.List;

import org.python.antlr.ParseException;
import org.python.antlr.Visitor;
import org.python.antlr.ast.Assign;
import org.python.antlr.ast.Name;
import org.python.antlr.ast.Suite;
import org.python.antlr.ast.Tuple;
import org.python.antlr.ast.arguments;
import org.python.antlr.ast.expr_contextType;
import org.python.antlr.ast.keyword;
import org.python.antlr.base.expr;
import org.python.antlr.base.stmt;

public class ArgListCompiler extends Visitor {
    public boolean arglist, keywordlist;
    public int posonlyargcount, kwonlyargcount;
    public List<expr> defaults;
    public List<keyword> kwDefaults = new ArrayList<keyword>();
    public List<keyword> annotations = new ArrayList<keyword>();
    public List<String> names = new ArrayList<String>();
    public List<String> fpnames = new ArrayList<String>();
    public List<stmt> init_code = new ArrayList<stmt>();

    public void reset() {
        arglist = keywordlist = false;
        posonlyargcount = kwonlyargcount = 0;
        defaults = null;
        names.clear();
        fpnames.clear();
        kwDefaults.clear();
        annotations.clear();
        init_code.clear();
    }

    public void appendInitCode(Suite node) {
        node.getInternalBody().addAll(0, init_code);
    }

    public List<expr> getDefaults() {
        return defaults;
    }

    public void visitArgs(arguments args) throws Exception {
        List<expr> positional = new ArrayList<expr>(args.getInternalPosonlyargs());
        posonlyargcount = positional.size();
        positional.addAll(args.getInternalArgs());
        for (expr parameter : positional) {
            String name = (String) visit(parameter);
            if (name == null) {
                throw new ParseException("invalid parameter", parameter);
            }
            names.add(name);
            if (parameter instanceof Tuple) {
                List<expr> targets = new ArrayList<expr>();
                targets.add(parameter);
                init_code.add(new Assign(parameter, targets,
                        new Name(parameter, name, expr_contextType.Load)));
            }
        }
        kwonlyargcount = args.getInternalKwonlyargs().size();
        if (kwonlyargcount != args.getInternalKw_defaults().size()) {
            throw new ParseException("keyword-only defaults must match keyword-only arguments", args);
        }
        for (int i = 0; i < kwonlyargcount; i++) {
            expr parameter = args.getInternalKwonlyargs().get(i);
            if (!(parameter instanceof Name)) {
                throw new ParseException("keyword-only argument must be a name", args);
            }
            String name = (String) visit(parameter);
            if (name == null) {
                throw new ParseException("invalid parameter", parameter);
            }
            names.add(name);
            expr value = args.getInternalKw_defaults().get(i);
            if (value != null) {
                kwDefaults.add(new keyword(parameter, name, value));
            }
        }
        if (args.getInternalVararg() != null) {
            arglist = true;
            names.add((String) visit(new Name(args, args.getInternalVararg(), expr_contextType.Param)));
        }
        if (args.getInternalKwarg() != null) {
            keywordlist = true;
            names.add((String) visit(new Name(args, args.getInternalKwarg(), expr_contextType.Param)));
        }
        defaults = args.getInternalDefaults();
        if (defaults.size() > positional.size()) {
            throw new ParseException("more positional defaults than arguments", args);
        }
        for (int i = 0; i < defaults.size(); i++) {
            if (defaults.get(i) == null) {
                throw new ParseException("non-default argument follows default argument",
                        positional.get(positional.size() - defaults.size() + i));
            }
        }
        annotations.addAll(args.getInternalAnnotations());
    }

    @Override
    public Object visitName(Name node) throws Exception {
        if (node.getInternalCtx() != expr_contextType.Store
                && node.getInternalCtx() != expr_contextType.Param) {
            return null;
        }
        String name = node.getInternalId();
        if ("__debug__".equals(name) || "None".equals(name)) {
            throw new ParseException("cannot assign to " + name, node);
        }
        if (fpnames.contains(name)) {
            throw new ParseException("duplicate argument name found: " + name, node);
        }
        fpnames.add(name);
        return name;
    }

    @Override
    public Object visitTuple(Tuple node) throws Exception {
        StringBuilder name = new StringBuilder("(");
        int n = node.getInternalElts().size();
        for (int i = 0; i < n - 1; i++) {
            name.append(visit(node.getInternalElts().get(i)));
            name.append(", ");
        }
        name.append(visit(node.getInternalElts().get(n - 1)));
        name.append(")");
        return name.toString();
    }
}
