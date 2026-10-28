package org.python.core;

/** Runtime operations for native JoinedStr and FormattedValue bytecode. */
public final class FStringSupport {
    private FStringSupport() {}

    public static PyUnicode join(PyObject[] parts) {
        StringBuilder result = new StringBuilder();
        for (PyObject part : parts) {
            result.append(asUnicode(part).getString());
        }
        return new PyUnicode(result.toString());
    }

    /** The value and all nested format fields have already been evaluated, left to right. */
    public static PyUnicode format(PyObject value, PyObject formatSpec, int conversion) {
        switch (conversion) {
            case 's':
                value = string(value);
                break;
            case 'r':
                value = representation(value);
                break;
            case 'a':
                value = ascii(representation(value));
                break;
            case -1:
                break;
            default:
                throw Py.ValueError("invalid f-string conversion");
        }
        if (value instanceof PyBoolean && formatSpec.__len__() == 0) {
            return new PyUnicode(value.toString());
        }
        // Do not use a global 'format' or evaluate a generated Python expression.
        // Preserve Python 3's object.__format__ rejection of non-empty specs here
        // without changing the retained Python 2 builtin format() implementation.
        if (value.getType().lookup("__format__") == PyObject.TYPE.lookup("__format__")) {
            if (formatSpec.__len__() != 0) {
                throw Py.TypeError("unsupported format string passed to "
                        + value.getType().fastGetName() + ".__format__");
            }
            return string(value);
        }
        return asUnicode(value.__format__(formatSpec));
    }

    private static PyUnicode asUnicode(PyObject value) {
        if (!(value instanceof PyString)) {
            throw Py.TypeError("__format__ must return a string, not "
                    + value.getType().fastGetName());
        }
        return value instanceof PyUnicode ? (PyUnicode)value : new PyUnicode((PyString)value);
    }

    private static PyUnicode string(PyObject value) {
        // The inherited Python 2 unicode.__str__ encodes to bytes, unlike Python 3 str.
        if (value instanceof PyUnicode
                && value.getType().lookup("__str__") == PyUnicode.TYPE.lookup("__str__")) {
            return new PyUnicode(((PyUnicode)value).getString());
        }
        return asUnicode(value.__str__());
    }

    private static PyUnicode representation(PyObject value) {
        if (!(value instanceof PyUnicode)
                || value.getType().lookup("__repr__") != PyUnicode.TYPE.lookup("__repr__")) {
            return asUnicode(value.__repr__());
        }
        // Python 3 text repr has no 'u' prefix and keeps printable Unicode characters.
        String text = ((PyUnicode)value).getString();
        char quote = text.indexOf('\'') >= 0 && text.indexOf('"') < 0 ? '"' : '\'';
        StringBuilder result = new StringBuilder().append(quote);
        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            i += Character.charCount(cp);
            if (cp == quote || cp == '\\') {
                result.append('\\').appendCodePoint(cp);
            } else if (cp == '\n') {
                result.append("\\n");
            } else if (cp == '\r') {
                result.append("\\r");
            } else if (cp == '\t') {
                result.append("\\t");
            } else if (printable(cp)) {
                result.appendCodePoint(cp);
            } else {
                escape(result, cp);
            }
        }
        return new PyUnicode(result.append(quote).toString());
    }

    private static boolean printable(int cp) {
        if (cp == ' ') {
            return true;
        }
        switch (Character.getType(cp)) {
            case Character.CONTROL:
            case Character.FORMAT:
            case Character.SURROGATE:
            case Character.PRIVATE_USE:
            case Character.UNASSIGNED:
            case Character.SPACE_SEPARATOR:
            case Character.LINE_SEPARATOR:
            case Character.PARAGRAPH_SEPARATOR:
                return false;
            default:
                return true;
        }
    }

    private static PyUnicode ascii(PyUnicode repr) {
        String text = repr.getString();
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            i += Character.charCount(cp);
            if (cp < 128) {
                result.append((char)cp);
            } else {
                escape(result, cp);
            }
        }
        return new PyUnicode(result.toString());
    }

    private static void escape(StringBuilder result, int cp) {
        int digits = cp <= 0xff ? 2 : cp <= 0xffff ? 4 : 8;
        result.append(digits == 2 ? "\\x" : digits == 4 ? "\\u" : "\\U");
        String hex = Integer.toHexString(cp);
        for (int i = hex.length(); i < digits; i++) {
            result.append('0');
        }
        result.append(hex);
    }
}
