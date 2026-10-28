package org.python.antlr;

import java.util.ArrayList;
import java.util.List;

import org.antlr.runtime.ANTLRStringStream;
import org.antlr.runtime.CommonToken;
import org.antlr.runtime.Token;
import org.python.antlr.ast.Expression;
import org.python.antlr.ast.FormattedValue;
import org.python.antlr.ast.JoinedStr;
import org.python.antlr.ast.Str;
import org.python.antlr.base.expr;
import org.python.core.CodeFlag;
import org.python.core.CompilerFlags;
import org.python.core.PyString;
import org.python.core.PyUnicode;

/** Parse PEP 498 replacement fields into native expression ASTs, never runtime eval calls. */
final class FStringParser {
    private final Token token;
    private final String text;
    private final int end;
    private final boolean raw;
    private final CompilerFlags flags;
    private int pos;

    static boolean isFormatted(String text) {
        int prefix = prefixLength(text);
        for (int i = 0; i < prefix; i++) {
            if (text.charAt(i) == 'f' || text.charAt(i) == 'F') {
                return true;
            }
        }
        return false;
    }

    static int prefixLength(String text) {
        int i = 0;
        while (i < text.length() && text.charAt(i) != '\'' && text.charAt(i) != '"') {
            i++;
        }
        return i;
    }

    FStringParser(Token token, String encoding, boolean printFunction, boolean unicodeLiterals) {
        this.token = token;
        text = token.getText();
        int prefix = prefixLength(text);
        raw = text.substring(0, prefix).toLowerCase(java.util.Locale.ROOT).contains("r");
        char quote = text.charAt(prefix);
        int quotes = prefix + 2 < text.length() && text.charAt(prefix + 1) == quote
                && text.charAt(prefix + 2) == quote ? 3 : 1;
        pos = prefix + quotes;
        end = text.length() - quotes;
        flags = new CompilerFlags();
        flags.encoding = encoding;
        if (printFunction) {
            flags.setFlag(CodeFlag.CO_FUTURE_PRINT_FUNCTION);
        }
        if (unicodeLiterals) {
            flags.setFlag(CodeFlag.CO_FUTURE_UNICODE_LITERALS);
        }
    }

    JoinedStr parse() {
        return new JoinedStr(token, parseParts(false, 0));
    }

    /** An adjacent ordinary literal is text, but raw prefixes must stay completely raw. */
    PyUnicode literal() {
        String value = text.substring(pos, end);
        if (!raw) {
            value = PyString.decode_UnicodeEscape(value, 0, value.length(), "strict", true);
        }
        return new PyUnicode(value);
    }

    private List<expr> parseParts(boolean formatSpec, int depth) {
        List<expr> values = new ArrayList<expr>();
        StringBuilder literal = new StringBuilder();
        int start = pos;
        while (pos < end) {
            char c = text.charAt(pos);
            if (c == '{') {
                if (!formatSpec && pos + 1 < end && text.charAt(pos + 1) == '{') {
                    literal.append('{');
                    pos += 2;
                } else {
                    flush(values, literal, start);
                    pos++;
                    parseField(values, depth);
                    start = pos;
                }
            } else if (c == '}') {
                if (formatSpec) {
                    break;
                }
                if (pos + 1 >= end || text.charAt(pos + 1) != '}') {
                    throw error("single '}' is not allowed", pos);
                }
                literal.append('}');
                pos += 2;
            } else if (c == '\\' && pos + 1 < end) {
                char next = text.charAt(pos + 1);
                if (next == '{' || next == '}') {
                    // A backslash never escapes a replacement-field delimiter.
                    literal.append(raw ? "\\" : "\\\\");
                    pos++;
                } else if (!raw && next == 'N' && pos + 2 < end
                        && text.charAt(pos + 2) == '{') {
                    int close = text.indexOf('}', pos + 3);
                    if (close < 0 || close >= end) {
                        throw error("malformed Unicode character name escape", pos);
                    }
                    literal.append(text, pos, close + 1);
                    pos = close + 1;
                } else {
                    literal.append(c).append(next);
                    pos += 2;
                }
            } else {
                literal.append(c);
                pos++;
            }
        }
        flush(values, literal, start);
        return values;
    }

    private void flush(List<expr> values, StringBuilder literal, int start) {
        if (literal.length() != 0) {
            String value = literal.toString();
            if (!raw) {
                value = PyString.decode_UnicodeEscape(value, 0, value.length(), "strict", true);
            }
            values.add(new Str(at(start), new PyUnicode(value)));
            literal.setLength(0);
        }
    }

    private void parseField(List<expr> values, int depth) {
        if (depth >= 2) {
            throw error("expressions nested too deeply", pos);
        }
        int start = pos;
        StringBuilder brackets = new StringBuilder();
        while (pos < end) {
            char c = text.charAt(pos);
            if (c == '\\') {
                throw error("expression part cannot include a backslash", pos);
            }
            if (c == '\'' || c == '"') {
                skipString(c);
                continue;
            }
            if (c == '#') {
                throw error("expression part cannot include '#'", pos);
            }
            if (c == '(' || c == '[' || c == '{') {
                brackets.append(c);
            } else if (c == ')' || c == ']' || c == '}') {
                if (brackets.length() == 0) {
                    if (c == '}') {
                        break;
                    }
                    throw error("unmatched '" + c + "'", pos);
                }
                char open = brackets.charAt(brackets.length() - 1);
                if ((c == ')' && open != '(') || (c == ']' && open != '[')
                        || (c == '}' && open != '{')) {
                    throw error("mismatched brackets", pos);
                }
                brackets.setLength(brackets.length() - 1);
            } else if (brackets.length() == 0) {
                if (c == ':' || (c == '!' && !followedByEquals())) {
                    break;
                }
                if (c == '=' && !followedByEquals()
                        && (pos == start || "=!<>".indexOf(text.charAt(pos - 1)) < 0)) {
                    break;
                }
            }
            pos++;
        }
        if (pos >= end) {
            throw error("expecting '}'", pos);
        }
        String source = text.substring(start, pos);
        if (source.trim().isEmpty()) {
            throw error("empty expression not allowed", start);
        }
        expr value = parseExpression(source, start);
        boolean debug = text.charAt(pos) == '=';
        if (debug) {
            pos++;
            while (pos < end && Character.isWhitespace(text.charAt(pos))) {
                pos++;
            }
            values.add(new Str(at(start), new PyUnicode(text.substring(start, pos))));
        }
        int conversion = -1;
        if (pos < end && text.charAt(pos) == '!') {
            pos++;
            if (pos >= end || "sra".indexOf(text.charAt(pos)) < 0) {
                throw error("invalid conversion character: expected 's', 'r', or 'a'", pos);
            }
            conversion = text.charAt(pos++);
        }
        JoinedStr spec = null;
        if (pos < end && text.charAt(pos) == ':') {
            pos++;
            spec = new JoinedStr(at(pos), parseParts(true, depth + 1));
        }
        if (pos >= end || text.charAt(pos) != '}') {
            throw error("expecting '}'", pos);
        }
        pos++;
        if (debug && conversion == -1 && spec == null) {
            conversion = 'r';
        }
        values.add(new FormattedValue(at(start), value, conversion, spec));
    }

    private boolean followedByEquals() {
        return pos + 1 < end && text.charAt(pos + 1) == '=';
    }

    private void skipString(char quote) {
        int quotes = pos + 2 < end && text.charAt(pos + 1) == quote
                && text.charAt(pos + 2) == quote ? 3 : 1;
        pos += quotes;
        while (pos < end) {
            char c = text.charAt(pos);
            if (c == '\\') {
                throw error("expression part cannot include a backslash", pos);
            }
            if (c == quote && (quotes == 1 || pos + 2 < end
                    && text.charAt(pos + 1) == quote && text.charAt(pos + 2) == quote)) {
                pos += quotes;
                return;
            }
            pos++;
        }
        throw error("unterminated string in expression", pos);
    }

    private expr parseExpression(String source, int start) {
        Token location = at(start);
        ANTLRStringStream stream = new ANTLRStringStream("(" + source + "\n)");
        stream.setLine(location.getLine());
        stream.setCharPositionInLine(location.getCharPositionInLine() - 1);
        try {
            return ((Expression)new BaseParser(stream, "<fstring>", flags)
                    .parseExpression()).getInternalBody();
        } catch (ParseException ex) {
            ParseException failure = new ParseException("f-string: " + ex.getMessage(),
                    ex.line, ex.charPositionInLine);
            failure.definite = true;
            throw failure;
        }
    }

    private Token at(int offset) {
        CommonToken result = new CommonToken(token);
        int line = token.getLine();
        int column = token.getCharPositionInLine();
        for (int i = 0; i < offset && i < text.length(); i++) {
            if (text.charAt(i) == '\n') {
                line++;
                column = 0;
            } else {
                column++;
            }
        }
        result.setLine(line);
        result.setCharPositionInLine(column);
        return result;
    }

    private ParseException error(String message, int offset) {
        return new ParseException("f-string: " + message, new PythonTree(at(offset)), true);
    }
}
