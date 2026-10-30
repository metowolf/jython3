package org.python.core;

import java.io.File;

/** Opt-in native Python 3 source roots, leaving the legacy stdlib in its own dialect. */
public final class Native3 {
    private Native3() {}

    public static boolean source(String filename) {
        String roots = System.getProperty("python.native3.path", "");
        if (roots.isEmpty() || filename == null || filename.startsWith("<")) {
            return false;
        }
        java.nio.file.Path file = new File(filename).toPath().toAbsolutePath().normalize();
        for (String root : roots.split(java.util.regex.Pattern.quote(File.pathSeparator))) {
            if (!root.isEmpty() && file.startsWith(new File(root).toPath().toAbsolutePath().normalize())) {
                return true;
            }
        }
        return false;
    }

    public static void configure(String filename, CompilerFlags flags) {
        if (source(filename)) {
            flags.setFlag(CodeFlag.CO_NATIVE3);
        }
        if (flags.isFlagSet(CodeFlag.CO_NATIVE3)) {
            flags.setFlag(CodeFlag.CO_FUTURE_PRINT_FUNCTION);
            flags.setFlag(CodeFlag.CO_FUTURE_UNICODE_LITERALS);
            flags.setFlag(CodeFlag.CO_FUTURE_ABSOLUTE_IMPORT);
            flags.setFlag(CodeFlag.CO_FUTURE_DIVISION);
        }
    }

    public static boolean frame(PyFrame frame) {
        return frame != null && frame.f_code != null
                && frame.f_code.co_flags.isFlagSet(CodeFlag.CO_NATIVE3);
    }

    public static void setupAnnotations(PyFrame frame) {
        if (frame.f_locals.__finditem__("__annotations__") == null) {
            frame.f_locals.__setitem__("__annotations__", new PyDictionary());
        }
    }

    public static void setAnnotation(PyFrame frame, String name, PyObject value) {
        frame.f_locals.__getitem__(Py.newString("__annotations__")).__setitem__(name, value);
    }

    public static PyObject builtins() {
        return imp.importName("_native3_builtins", true).__getattr__("namespace");
    }
}
