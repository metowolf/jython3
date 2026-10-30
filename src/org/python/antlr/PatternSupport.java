package org.python.antlr;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.antlr.runtime.Token;
import org.python.antlr.ast.*;
import org.python.antlr.base.expr;
import org.python.antlr.base.pattern;
import org.python.core.Py;

/** First structural matching subset. Unsupported patterns fail at compile time. */
public final class PatternSupport {
    private PatternSupport() {}

    public static pattern fromExpression(expr value) {
        if (value instanceof Name) {
            String name = ((Name)value).getInternalId();
            if ("None".equals(name)) return new MatchSingleton(value, Py.None);
            if ("True".equals(name)) return new MatchSingleton(value, Py.True);
            if ("False".equals(name)) return new MatchSingleton(value, Py.False);
            return new MatchAs(value, null, "_".equals(name) ? null : name);
        }
        if (value instanceof BinOp && ((BinOp)value).getInternalOp() == operatorType.BitOr) {
            List<pattern> choices = new ArrayList<pattern>();
            flatten(value, choices);
            return new MatchOr(value, choices);
        }
        if (validValue(value)) return new MatchValue(value, value);
        throw new ParseException("unsupported match pattern (expected literal, value or capture)", value);
    }

    private static void flatten(expr value, List<pattern> choices) {
        if (value instanceof BinOp && ((BinOp)value).getInternalOp() == operatorType.BitOr) {
            flatten(((BinOp)value).getInternalLeft(), choices);
            flatten(((BinOp)value).getInternalRight(), choices);
        } else choices.add(fromExpression(value));
    }

    private static boolean dotted(expr value) {
        return value instanceof Name || value instanceof Attribute && dotted(((Attribute)value).getInternalValue());
    }

    private static boolean validValue(expr value) {
        return value instanceof Num || value instanceof Str
                || value instanceof Attribute && dotted(value)
                || value instanceof UnaryOp && ((UnaryOp)value).getInternalOp() == unaryopType.USub
                && ((UnaryOp)value).getInternalOperand() instanceof Num;
    }

    public static pattern capture(Token token, pattern inner) {
        String name = token.getText();
        if ("_".equals(name) || "None".equals(name) || "True".equals(name) || "False".equals(name)) {
            throw new ParseException("invalid capture target", new Name(token, name, expr_contextType.Store));
        }
        return new MatchAs(token, inner, name);
    }

    public static boolean validate(pattern value) {
        return validate(value, new HashSet<String>());
    }

    private static boolean validate(pattern value, Set<String> bound) {
        if (value == null) throw new ParseException("pattern is required");
        if (value instanceof MatchValue) {
            if (!validValue(((MatchValue)value).getInternalValue())) {
                throw new ParseException("invalid value pattern", value);
            }
            return false;
        }
        if (value instanceof MatchSingleton) {
            Object constant = ((MatchSingleton)value).getInternalValue();
            if (constant != Py.None && constant != Py.True && constant != Py.False) {
                throw new ParseException("singleton pattern must be None, True or False", value);
            }
            return false;
        }
        if (value instanceof MatchAs) {
            MatchAs capture = (MatchAs)value;
            boolean irrefutable = capture.getInternalPattern() == null
                    || validate(capture.getInternalPattern(), bound);
            String name = capture.getInternalName();
            if (name != null && ("_".equals(name) || !bound.add(name))) {
                throw new ParseException("invalid or repeated capture name", value);
            }
            return irrefutable;
        }
        if (value instanceof MatchOr) {
            List<pattern> choices = ((MatchOr)value).getInternalPatterns();
            if (choices.size() < 2) throw new ParseException("OR pattern needs at least two alternatives", value);
            Set<String> names = null;
            boolean irrefutable = false;
            for (pattern choice : choices) {
                if (irrefutable) throw new ParseException("irrefutable OR alternative is not last", choice);
                Set<String> current = new HashSet<String>();
                irrefutable = validate(choice, current);
                if (names == null) names = current;
                else if (!names.equals(current)) throw new ParseException("alternative patterns bind different names", choice);
            }
            for (String name : names) {
                if (!bound.add(name)) throw new ParseException("repeated capture name", value);
            }
            return irrefutable;
        }
        throw new ParseException("unsupported match pattern", value);
    }
}
