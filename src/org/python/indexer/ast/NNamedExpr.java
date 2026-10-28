package org.python.indexer.ast;

import org.python.indexer.Scope;
import org.python.indexer.types.NType;
import org.python.indexer.types.NUnknownType;

/** An expression binding a name and evaluating to the assigned value. */
public class NNamedExpr extends NNode {
    private static final long serialVersionUID = 1L;
    public NNode target;
    public NNode value;

    public NNamedExpr(NNode target, NNode value, int start, int end) {
        super(start, end);
        this.target = target;
        this.value = value;
        addChildren(target, value);
    }

    @Override
    public boolean bindsName() { return true; }

    @Override
    protected void bindNames(Scope scope) throws Exception {
        NameBinder.make().bind(scope, target, new NUnknownType());
    }

    @Override
    public NType resolve(Scope scope) throws Exception {
        NType type = resolveExpr(value, scope);
        NameBinder.make().bind(scope, target, type);
        return setType(type);
    }

    @Override
    public void visit(NNodeVisitor visitor) {
        if (visitor.visit(this)) {
            visitNode(target, visitor);
            visitNode(value, visitor);
        }
    }

    @Override
    public String toString() {
        return "<NamedExpr:" + target + ":=" + value + ">";
    }
}
