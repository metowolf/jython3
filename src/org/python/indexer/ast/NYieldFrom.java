/**
 * Copyright 2009, Google Inc.  All rights reserved.
 * Licensed to PSF under a Contributor Agreement.
 */
package org.python.indexer.ast;

import org.python.indexer.Scope;
import org.python.indexer.types.NUnknownType;
import org.python.indexer.types.NType;

public class NYieldFrom extends NNode {

    static final long serialVersionUID = 2639481204205358048L;

    public NNode value;

    public NYieldFrom(NNode n) {
        this(n, 0, 1);
    }

    public NYieldFrom(NNode n, int start, int end) {
        super(start, end);
        this.value = n;
        addChildren(n);
    }

    @Override
    public NType resolve(Scope s) throws Exception {
        resolveExpr(value, s);
        return setType(new NUnknownType());
    }

    @Override
    public String toString() {
        return "<YieldFrom:" + start() + ":" + value + ">";
    }

    @Override
    public void visit(NNodeVisitor v) {
        if (v.visit(this)) {
            visitNode(value, v);
        }
    }
}
