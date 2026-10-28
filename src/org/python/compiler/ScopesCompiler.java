// (C) Copyright 2001 Samuele Pedroni

package org.python.compiler;

import org.python.antlr.Visitor;
import org.python.antlr.PythonTree;
import org.python.antlr.ast.ClassDef;
import org.python.antlr.ast.Call;
import org.python.antlr.ast.Assign;
import org.python.antlr.ast.AugAssign;
import org.python.antlr.ast.BinOp;
import org.python.antlr.ast.Delete;
import org.python.antlr.ast.For;
import org.python.antlr.ast.Dict;
import org.python.antlr.ast.DictComp;
import org.python.antlr.ast.Exec;
import org.python.antlr.ast.Expression;
import org.python.antlr.ast.FormattedValue;
import org.python.antlr.ast.FunctionDef;
import org.python.antlr.ast.GeneratorExp;
import org.python.antlr.ast.Global;
import org.python.antlr.ast.JoinedStr;
import org.python.antlr.ast.Str;
import org.python.antlr.ast.Import;
import org.python.antlr.ast.ImportFrom;
import org.python.antlr.ast.Interactive;
import org.python.antlr.ast.Lambda;
import org.python.antlr.ast.ListComp;
import org.python.antlr.ast.Name;
import org.python.antlr.ast.Nonlocal;
import org.python.antlr.ast.Raise;
import org.python.antlr.ast.Return;
import org.python.antlr.ast.SetComp;
import org.python.antlr.ast.Tuple;
import org.python.antlr.ast.With;
import org.python.antlr.ast.Yield;
import org.python.antlr.ast.Starred;
import org.python.antlr.ast.Attribute;
import org.python.antlr.ast.Subscript;
import org.python.antlr.ast.Set;
import org.python.antlr.ast.arguments;
import org.python.antlr.ast.comprehension;
import org.python.antlr.ast.expr_contextType;
import org.python.antlr.ast.keyword;
import org.python.antlr.ast.operatorType;
import org.python.antlr.base.expr;
import org.python.antlr.base.stmt;
import org.python.core.ParserFacade;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Hashtable;
import java.util.Stack;
import java.util.List;

public class ScopesCompiler extends Visitor implements ScopeConstants {

    private CompilationContext code_compiler;

    private Stack<ScopeInfo> scopes;
    private ScopeInfo cur = null;
    private Hashtable<PythonTree,ScopeInfo> nodeScopes;

    private int level = 0;
    private int func_level = 0;

    public ScopesCompiler(CompilationContext code_compiler, Hashtable<PythonTree,ScopeInfo> nodeScopes) {
        this.code_compiler = code_compiler;
        this.nodeScopes = nodeScopes;
        scopes = new Stack<ScopeInfo>();
    }

    public void beginScope(String name, int kind, PythonTree node,
            ArgListCompiler ac) {
        if (cur != null) {
            scopes.push(cur);
        }
        if (kind == FUNCSCOPE) {
            func_level++;
        }
        cur = new ScopeInfo(name, node, level++, kind, func_level, ac);
        nodeScopes.put(node, cur);
    }

    public void endScope() throws Exception {
        if (cur.kind == FUNCSCOPE) {
            func_level--;
        }
        level--;
        ScopeInfo up = null;
        if (!scopes.empty()) {
            up = scopes.pop();
        }
        //Go into the stack to find a non class containing scope to use making the closure
        //See PEP 227
        int dist = 1;
        ScopeInfo referenceable = up;
        for (int i = scopes.size() - 1; i >= 0
                && referenceable.kind == CLASSSCOPE; i--, dist++) {
            referenceable = (scopes.get(i));
        }
        cur.cook(referenceable, dist, code_compiler);
        cur.dump(); // debug
        cur = up;
    }

    public void parse(PythonTree node) throws Exception {
        try {
            visit(node);
            // Outer bindings may follow the nested function's definition in source order.
            for (ScopeInfo scope : nodeScopes.values()) {
                scope.validateNonlocals(code_compiler);
            }
        } catch (Throwable t) {
            throw ParserFacade.fixParseError(null, t, code_compiler.getFilename());
        }
    }

    @Override
    public Object visitInteractive(Interactive node) throws Exception {
        beginScope("<single-top>", TOPSCOPE, node, null);
        suite(node.getInternalBody());
        endScope();
        return null;
    }

    @Override
    public Object visitModule(org.python.antlr.ast.Module node)
            throws Exception {
        beginScope("<file-top>", TOPSCOPE, node, null);
        suite(node.getInternalBody());
        endScope();
        return null;
    }

    @Override
    public Object visitExpression(Expression node) throws Exception {
        beginScope("<eval-top>", TOPSCOPE, node, null);
        visit(new Return(node,node.getInternalBody()));
        endScope();
        return null;
    }

    private void def(String name) {
        cur.addBound(name);
    }

    private void visitDecorators(List<expr> decorators, PythonTree owner) throws Exception {
        for (expr decorator : decorators) {
            if (decorator == null || expressionContext(decorator) != expr_contextType.Load) {
                code_compiler.error("decorator must have a value in Load context", true, owner);
            }
            visit(decorator);
        }
    }

    @Override
    public Object visitFunctionDef(FunctionDef node) throws Exception {
        def(node.getInternalName());
        ArgListCompiler ac = new ArgListCompiler();
        ac.visitArgs(node.getInternalArgs());

        visitDecorators(node.getInternalDecorator_list(), node);
        for (expr value : ac.getDefaults()) {
            visit(value);
        }
        for (keyword value : ac.kwDefaults) {
            visit(value.getInternalValue());
        }
        for (keyword annotation : ac.annotations) {
            visit(annotation.getInternalValue());
        }
        if (node.getInternalReturns() != null) {
            visit(node.getInternalReturns());
        }

        beginScope(node.getInternalName(), FUNCSCOPE, node, ac);
        int n = ac.names.size();
        for (int i = 0; i < n; i++) {
            cur.addParam(ac.names.get(i));
        }
        for (int i = 0; i < ac.init_code.size(); i++) {
            visit(ac.init_code.get(i));
        }
        cur.markFromParam();
        suite(node.getInternalBody());
        endScope();
        return null;
    }

    @Override
    public Object visitLambda(Lambda node) throws Exception {
        ArgListCompiler ac = new ArgListCompiler();
        ac.visitArgs(node.getInternalArgs());

        List<? extends PythonTree> defaults = ac.getDefaults();
        for (int i = 0; i < defaults.size(); i++) {
            visit(defaults.get(i));
        }
        for (keyword value : ac.kwDefaults) {
            visit(value.getInternalValue());
        }

        beginScope("<lambda>", FUNCSCOPE, node, ac);
        for (Object o : ac.names) {
            cur.addParam((String) o);
        }
        for (Object o : ac.init_code) {
            visit((stmt) o);
        }
        cur.markFromParam();
        visit(node.getInternalBody());
        endScope();
        return null;
    }

    public void suite(List<stmt> stmts) throws Exception {
        for (int i = 0; i < stmts.size(); i++)
            visit(stmts.get(i));
    }

    @Override
    public Object visitImport(Import node) throws Exception {
        for (int i = 0; i < node.getInternalNames().size(); i++) {
            if (node.getInternalNames().get(i).getInternalAsname() != null) {
                cur.addBound(node.getInternalNames().get(i).getInternalAsname());
            } else {
                String name = node.getInternalNames().get(i).getInternalName();
                if (name.indexOf('.') > 0) {
                    name = name.substring(0, name.indexOf('.'));
                }
                cur.addBound(name);
            }
        }
        return null;
    }

    @Override
    public Object visitImportFrom(ImportFrom node) throws Exception {
        Future.checkFromFuture(node); // future stmt support
        int n = node.getInternalNames().size();
        if (n == 0) {
            cur.from_import_star = true;
            return null;
        }
        for (int i = 0; i < n; i++) {
            if (node.getInternalNames().get(i).getInternalAsname() != null) {
                cur.addBound(node.getInternalNames().get(i).getInternalAsname());
            } else {
                cur.addBound(node.getInternalNames().get(i).getInternalName());
            }
        }
        return null;
    }

    private void visitCallValue(expr value, PythonTree owner) throws Exception {
        if (value == null || expressionContext(value) != expr_contextType.Load) {
            code_compiler.error("call expression must have a value in Load context", true, owner);
        }
        visit(value);
    }

    @Override
    public Object visitCall(Call node) throws Exception {
        visitCallValue(node.getInternalFunc(), node);
        boolean modern = false;
        for (expr argument : node.getInternalArgs()) {
            if (argument instanceof Starred) {
                modern = true;
                Starred star = (Starred)argument;
                if (star.getInternalCtx() != expr_contextType.Load) {
                    code_compiler.error("call star must have Load context", true, star);
                }
                visitCallValue(star.getInternalValue(), star);
            } else {
                visitCallValue(argument, node);
            }
        }
        java.util.Set<String> names = new java.util.HashSet<String>();
        for (keyword key : node.getInternalKeywords()) {
            if (key == null) {
                code_compiler.error("call keyword must not be null", true, node);
            }
            String name = key.getInternalArg();
            if (name == null) {
                modern = true;
            } else if ("None".equals(name) || "True".equals(name) || "False".equals(name)
                    || "__debug__".equals(name)) {
                code_compiler.error("invalid explicit keyword name: " + name, true, key);
            } else if (!names.add(name)) {
                code_compiler.error("keyword arguments repeated", true, key);
            }
            visitCallValue(key.getInternalValue(), key);
        }
        if (modern && (node.getInternalStarargs() != null || node.getInternalKwargs() != null)) {
            code_compiler.error("cannot mix modern call unpacking with legacy starargs/kwargs", true, node);
        }
        if (node.getInternalStarargs() != null) visitCallValue(node.getInternalStarargs(), node);
        if (node.getInternalKwargs() != null) visitCallValue(node.getInternalKwargs(), node);
        return null;
    }

    @Override
    public Object visitStarred(Starred node) throws Exception {
        code_compiler.error("starred expression is not allowed here", true, node);
        return null;
    }

    private Object visitUnpackingSequence(List<expr> elements, expr_contextType context)
            throws Exception {
        boolean starred = false;
        for (expr element : elements) {
            if (element instanceof Starred) {
                Starred star = (Starred)element;
                if (context != expr_contextType.Load && context != expr_contextType.Store) {
                    code_compiler.error("starred expression is not allowed in this context", true, star);
                }
                if (star.getInternalCtx() != context || star.getInternalValue() == null) {
                    code_compiler.error("invalid starred expression context or value", true, star);
                }
                if (context == expr_contextType.Store) {
                    if (starred) {
                        code_compiler.error("multiple starred expressions in assignment", true, star);
                    }
                    validateStarTarget(star.getInternalValue());
                } else if (expressionContext(star.getInternalValue()) != expr_contextType.Load) {
                    code_compiler.error("starred iterable must have Load context", true, star);
                }
                starred = true;
                visit(star.getInternalValue());
            } else {
                visit(element);
            }
        }
        return null;
    }

    private expr_contextType expressionContext(expr value) {
        if (value instanceof Name) {
            return ((Name)value).getInternalCtx();
        } else if (value instanceof Attribute) {
            return ((Attribute)value).getInternalCtx();
        } else if (value instanceof Subscript) {
            return ((Subscript)value).getInternalCtx();
        } else if (value instanceof Tuple) {
            return ((Tuple)value).getInternalCtx();
        } else if (value instanceof org.python.antlr.ast.List) {
            return ((org.python.antlr.ast.List)value).getInternalCtx();
        } else if (value instanceof Starred) {
            return ((Starred)value).getInternalCtx();
        }
        return expr_contextType.Load;
    }

    private void validateStarTarget(expr target) throws Exception {
        List<expr> children = null;
        if (target instanceof Name) {
            String name = ((Name)target).getInternalId();
            if ("None".equals(name) || "True".equals(name) || "False".equals(name)) {
                code_compiler.error("cannot assign to " + name, true, target);
            }
        } else if (target instanceof Tuple) {
            children = ((Tuple)target).getInternalElts();
        } else if (target instanceof org.python.antlr.ast.List) {
            children = ((org.python.antlr.ast.List)target).getInternalElts();
        } else if (!(target instanceof Attribute || target instanceof Subscript)) {
            code_compiler.error("invalid starred assignment target", true, target);
            return;
        }
        if (expressionContext(target) != expr_contextType.Store) {
            code_compiler.error("starred assignment target must have Store context", true, target);
        }
        if (children != null) {
            for (expr child : children) {
                validateStarTarget(child instanceof Starred ? ((Starred)child).getInternalValue()
                        : child);
            }
        }
    }

    @Override
    public Object visitTuple(Tuple node) throws Exception {
        return visitUnpackingSequence(node.getInternalElts(), node.getInternalCtx());
    }

    @Override
    public Object visitList(org.python.antlr.ast.List node) throws Exception {
        return visitUnpackingSequence(node.getInternalElts(), node.getInternalCtx());
    }

    @Override
    public Object visitSet(Set node) throws Exception {
        return visitUnpackingSequence(node.getInternalElts(), expr_contextType.Load);
    }

    private void checkDictTarget(expr target) throws Exception {
        if (target instanceof Dict) {
            code_compiler.error("dict display cannot be an assignment or deletion target", true, target);
        } else if (target instanceof Tuple) {
            for (expr child : ((Tuple)target).getInternalElts()) {
                checkDictTarget(child);
            }
        } else if (target instanceof org.python.antlr.ast.List) {
            for (expr child : ((org.python.antlr.ast.List)target).getInternalElts()) {
                checkDictTarget(child);
            }
        } else if (target instanceof Starred) {
            checkDictTarget(((Starred)target).getInternalValue());
        }
    }

    @Override
    public Object visitAssign(Assign node) throws Exception {
        for (expr target : node.getInternalTargets()) {
            checkDictTarget(target);
        }
        traverse(node);
        return null;
    }

    private void validateMatmulOperand(expr value, PythonTree owner) throws Exception {
        if (value == null || expressionContext(value) != expr_contextType.Load) {
            code_compiler.error("matrix operand must have a value in Load context", true, owner);
        }
    }

    @Override
    public Object visitBinOp(BinOp node) throws Exception {
        if (node.getInternalOp() == operatorType.MatMult) {
            validateMatmulOperand(node.getInternalLeft(), node);
            validateMatmulOperand(node.getInternalRight(), node);
        }
        traverse(node);
        return null;
    }

    @Override
    public Object visitAugAssign(AugAssign node) throws Exception {
        if (node.getInternalOp() == operatorType.MatMult) {
            expr target = node.getInternalTarget();
            if (!(target instanceof Name || target instanceof Attribute || target instanceof Subscript)
                    || expressionContext(target) != expr_contextType.Store
                    && expressionContext(target) != expr_contextType.AugStore) {
                code_compiler.error("invalid matrix augmented-assignment target", true, node);
            }
            validateMatmulOperand(node.getInternalValue(), node);
        }
        checkDictTarget(node.getInternalTarget());
        traverse(node);
        return null;
    }

    @Override
    public Object visitDelete(Delete node) throws Exception {
        for (expr target : node.getInternalTargets()) {
            checkDictTarget(target);
        }
        traverse(node);
        return null;
    }

    @Override
    public Object visitFor(For node) throws Exception {
        checkDictTarget(node.getInternalTarget());
        traverse(node);
        return null;
    }

    @Override
    public Object visitDict(Dict node) throws Exception {
        List<expr> keys = node.getInternalKeys();
        List<expr> values = node.getInternalValues();
        if (keys == null || values == null || keys.size() != values.size()) {
            code_compiler.error("Dict keys and values must have the same length", true, node);
        }
        for (int i = 0; i < keys.size(); i++) {
            expr key = keys.get(i);
            expr value = values.get(i);
            if (value == null) {
                code_compiler.error("Dict value must not be null", true, node);
            }
            if (key != null) {
                if (expressionContext(key) != expr_contextType.Load) {
                    code_compiler.error("Dict key must have Load context", true, key);
                }
                visit(key);
            }
            if (expressionContext(value) != expr_contextType.Load) {
                code_compiler.error("Dict value must have Load context", true, value);
            }
            visit(value);
        }
        return null;
    }

    @Override
    public Object visitJoinedStr(JoinedStr node) throws Exception {
        for (expr value : node.getInternalValues()) {
            if (!(value instanceof Str || value instanceof FormattedValue)) {
                code_compiler.error("JoinedStr values must be strings or FormattedValue nodes",
                        true, node);
            }
        }
        traverse(node);
        return null;
    }

    @Override
    public Object visitFormattedValue(FormattedValue node) throws Exception {
        Integer conversion = node.getInternalConversion();
        if (node.getInternalValue() == null || conversion == null
                || conversion != -1 && conversion != 's' && conversion != 'r' && conversion != 'a') {
            code_compiler.error("invalid FormattedValue value or conversion", true, node);
        }
        if (node.getInternalFormat_spec() != null
                && !(node.getInternalFormat_spec() instanceof JoinedStr)) {
            code_compiler.error("FormattedValue format_spec must be a JoinedStr", true, node);
        }
        traverse(node);
        return null;
    }

    @Override
    public Object visitRaise(Raise node) throws Exception {
        if (node.getInternalCause() != null
                && (node.getInternalType() == null || node.getInternalInst() != null
                || node.getInternalTback() != null)) {
            code_compiler.error("raise from requires an exception and no legacy arguments", true, node);
        }
        traverse(node);
        return null;
    }

    @Override
    public Object visitGlobal(Global node) throws Exception {
        int n = node.getInternalNames().size();
        for (int i = 0; i < n; i++) {
            String name = node.getInternalNames().get(i);
            int prev = cur.addGlobal(name);
            if (prev >= 0) {
                if ((prev & NONLOCAL) != 0) {
                    code_compiler.error("name '" + name + "' is nonlocal and global", true, node);
                }
                if ((prev & FROM_PARAM) != 0) {
                    code_compiler.error("name '" + name
                            + "' is local and global", true, node);
                }
                if ((prev & GLOBAL) != 0) {
                    continue;
                }
                String what;
                if ((prev & BOUND) != 0) {
                    what = "assignment";
                } else {
                    what = "use";
                }
                code_compiler.error("name '" + name
                        + "' declared global after " + what, false, node);
            }
        }
        return null;
    }

    @Override
    public Object visitNonlocal(Nonlocal node) throws Exception {
        if (cur.kind == TOPSCOPE) {
            code_compiler.error("nonlocal declaration not allowed at module level", true, node);
        }
        if (node.getInternalNames() == null || node.getInternalNames().isEmpty()) {
            code_compiler.error("nonlocal declaration requires a name", true, node);
        }
        for (String name : node.getInternalNames()) {
            if (name == null || name.equals("None") || name.equals("__debug__")) {
                code_compiler.error("invalid nonlocal name", true, node);
            }
            SymInfo previous = cur.tbl.get(name);
            if (previous != null) {
                int flags = previous.flags;
                if ((flags & NONLOCAL) != 0 && (flags & (NONLOCAL_USED | NONLOCAL_ASSIGNED)) == 0) {
                    continue;
                }
                if ((flags & GLOBAL) != 0) {
                    code_compiler.error("name '" + name + "' is nonlocal and global", true, node);
                }
                if ((flags & PARAM) != 0) {
                    code_compiler.error("name '" + name + "' is parameter and nonlocal", true, node);
                }
                code_compiler.error("name '" + name + "' is "
                        + ((flags & (BOUND | NONLOCAL_ASSIGNED)) != 0 ? "assigned to" : "used")
                        + " prior to nonlocal declaration", true, node);
            }
            cur.addNonlocal(name, node);
        }
        return null;
    }

    @Override
    public Object visitExec(Exec node) throws Exception {
        cur.exec = true;
        if (node.getInternalGlobals() == null && node.getInternalLocals() == null) {
            cur.unqual_exec = true;
        }
        traverse(node);
        return null;
    }

    @Override
    public Object visitClassDef(ClassDef node) throws Exception {
        visitDecorators(node.getInternalDecorator_list(), node);
        def(node.getInternalName());
        for (expr base : node.getInternalBases()) {
            expr value = base;
            if (base instanceof Starred) {
                Starred star = (Starred)base;
                if (star.getInternalCtx() != expr_contextType.Load) {
                    code_compiler.error("class base star must have Load context", true, star);
                }
                value = star.getInternalValue();
            }
            if (value == null || expressionContext(value) != expr_contextType.Load) {
                code_compiler.error("class base must have a value in Load context", true, node);
            }
            visit(value);
        }
        beginScope(node.getInternalName(), CLASSSCOPE, node, null);
        suite(node.getInternalBody());
        endScope();
        return null;
    }

    @Override
    public Object visitName(Name node) throws Exception {
        String name = node.getInternalId();
        if (node.getInternalCtx() != expr_contextType.Load) {
            if (name.equals("__debug__")) {
                code_compiler.error("can not assign to __debug__", true, node);
            }
            cur.addBound(name);
        } else {
            cur.addUsed(name);
        }
        return null;
    }

    @Override
    public Object visitListComp(ListComp node) throws Exception {
        for (comprehension generator : node.getInternalGenerators()) {
            checkDictTarget(generator.getInternalTarget());
        }
        String tmp = "_[" + node.getLineno() + "_" + node.getCol_offset()
                + "]";
        cur.addBound(tmp);
        traverse(node);
        return null;
    }

    @Override
    public Object visitDictComp(DictComp node) throws Exception {
        java.util.List<expr> kv = Arrays.asList(node.getInternalKey(), node.getInternalValue());
        return visitInternalGenerators(
                node, new Tuple(node, kv, expr_contextType.UNDEFINED), node.getInternalGenerators());
    }

    @Override
    public Object visitSetComp(SetComp node) throws Exception {
        return visitInternalGenerators(node, node.getInternalElt(), node.getInternalGenerators());
    }

    @Override
    public Object visitYield(Yield node) throws Exception {
        cur.defineAsGenerator(node);
        cur.yield_count++;
        traverse(node);
        return null;
    }

    @Override
    public Object visitReturn(Return node) throws Exception {
        if (node.getInternalValue() != null) {
            cur.noteReturnValue(node);
        }
        traverse(node);
        return null;
    }

    private Object visitInternalGenerators(expr node, expr elt, java.util.List<comprehension> generators)
            throws Exception {
        // The first iterator is evaluated in the outer scope
        if (generators != null && generators.size() > 0) {
            visit(generators.get(0).getInternalIter());
        }
        String bound_exp = "_(x)";
        String tmp = "_(" + node.getLineno() + "_" + node.getCol_offset()
                + ")";
        def(tmp);
        ArgListCompiler ac = new ArgListCompiler();
        List<expr> args = new ArrayList<expr>();
        args.add(new Name(node.getToken(), bound_exp, expr_contextType.Param));
        ac.visitArgs(new arguments(node, args, null, null, new ArrayList<expr>()));
        beginScope(tmp, FUNCSCOPE, node, ac);
        cur.addParam(bound_exp);
        cur.markFromParam();

        cur.defineAsGenerator(node);
        cur.yield_count++;
        // The reset of the iterators are evaluated in the inner scope
        if (elt != null) {
            visit(elt);
        }
        if (generators != null) {
            for (int i = 0; i < generators.size(); i++) {
                if (generators.get(i) != null) {
                    checkDictTarget(generators.get(i).getInternalTarget());
                    if (i == 0) {
                        visit(generators.get(i).getInternalTarget());
                        if (generators.get(i).getInternalIfs() != null) {
                            for (expr cond : generators.get(i).getInternalIfs()) {
                                if (cond != null) {
                                    visit(cond);
                                }
                            }
                        }
                    } else {
                        visit(generators.get(i));
                    }
                }
            }
        }

        endScope();
        return null;
    }

    @Override
    public Object visitGeneratorExp(GeneratorExp node) throws Exception {
        return visitInternalGenerators(node, node.getInternalElt(), node.getInternalGenerators());
    }

    @Override
    public Object visitWith(With node) throws Exception {
        checkDictTarget(node.getInternalOptional_vars());
        cur.max_with_count++;
        traverse(node);

        return null;
    }

}