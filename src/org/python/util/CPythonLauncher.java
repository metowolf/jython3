package org.python.util;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Optional, out-of-process CPython backend. This is not a PythonInterpreter
 * implementation and does not expose Java objects to Python. No Jython classes
 * or Python 2 library paths are needed by this launcher.
 */
public final class CPythonLauncher {
    public static final String VERSION = "3.15.2";
    public static final String EXECUTABLE_PROPERTY = "python.cpython.executable";
    public static final String EXECUTABLE_ENV = "JYTHON_CPYTHON_EXECUTABLE";
    private static final String VERSION_MARKER = "cpython:3.15.2:final:0";
    private static final String VERSION_CHECK = "import sys; "
            + "ok = sys.implementation.name == 'cpython' and "
            + "tuple(sys.version_info) == (3, 15, 2, 'final', 0); "
            + "print('" + VERSION_MARKER + "' if ok else sys.version); "
            + "sys.exit(0 if ok else 1)";

    private CPythonLauncher() {}

    /** CLI entry point. Python exit codes are preserved; launcher errors use 2. */
    public static void main(String[] args) {
        System.exit(run(args));
    }

    /**
     * Run with inherited OS stdin/stdout/stderr and current working directory.
     * Applications needing captured output may use {@link #processBuilder}.
     */
    public static int run(String... args) {
        Process process = null;
        Thread shutdownHook = null;
        try {
            process = processBuilder(args).inheritIO().start();
            final Process child = process;
            shutdownHook = new Thread(() -> terminate(child), "cpython-shutdown");
            Runtime.getRuntime().addShutdownHook(shutdownHook);
            return process.waitFor();
        } catch (InterruptedException error) {
            if (process != null) {
                terminate(process);
            }
            Thread.currentThread().interrupt();
            return 130;
        } catch (IOException | IllegalArgumentException | SecurityException error) {
            System.err.println("CPython backend: " + error.getMessage());
            return 2;
        } finally {
            if (process != null && process.isAlive()) {
                terminate(process);
            }
            if (shutdownHook != null) {
                try {
                    Runtime.getRuntime().removeShutdownHook(shutdownHook);
                } catch (IllegalStateException ignored) {
                    // JVM shutdown has already begun; the hook owns cleanup.
                }
            }
        }
    }

    /**
     * Verify the configured interpreter, then return a builder with piped I/O.
     * Each argument is passed literally, without a shell. The caller owns the
     * child lifecycle and must consume/redirect both stdout and stderr.
     * Properties are read on each call, before the child is created.
     */
    public static ProcessBuilder processBuilder(String... args)
            throws IOException, InterruptedException {
        File executable = executable();
        verify(executable);
        return builder(executable, args);
    }

    private static File executable() throws IOException {
        String configured = System.getProperty(EXECUTABLE_PROPERTY);
        if (configured == null) {
            configured = System.getenv(EXECUTABLE_ENV);
        }
        File executable;
        if (configured != null) {
            if (configured.trim().isEmpty()) {
                throw new IOException("Empty CPython executable path");
            }
            executable = new File(configured);
        } else {
            String home = System.getProperty("python.home");
            File root;
            if (home != null) {
                root = new File(home);
            } else {
                try {
                    File location = new File(CPythonLauncher.class.getProtectionDomain()
                            .getCodeSource().getLocation().toURI());
                    root = location.isFile() ? location.getParentFile() : new File("dist");
                } catch (URISyntaxException | NullPointerException error) {
                    throw new IOException("Set -D" + EXECUTABLE_PROPERTY
                            + " to the CPython 3.15.2 executable", error);
                }
            }
            String suffix = File.separatorChar == '\\' ? "python.exe" : "bin/python3.15";
            executable = new File(new File(root, "cpython"), suffix);
        }
        executable = executable.getAbsoluteFile();
        if (!executable.isFile() || !executable.canExecute()) {
            throw new IOException("Executable not found or not executable: " + executable
                    + ". Run python3 tools/install_cpython.py or set -D"
                    + EXECUTABLE_PROPERTY + "=/path/to/python3.15 (or " + EXECUTABLE_ENV + ").");
        }
        return executable;
    }

    private static ProcessBuilder builder(File executable, String... args) {
        List<String> command = new ArrayList<>();
        command.add(executable.getPath());
        command.addAll(Arrays.asList(args));
        ProcessBuilder builder = new ProcessBuilder(command);
        Map<String, String> environment = builder.environment();
        // Never load the adjacent Jython 2.7 library into CPython. Explicit
        // CPython-only module paths may be supplied via the namespaced variable.
        environment.remove("PYTHONHOME");
        environment.remove("PYTHONPATH");
        environment.remove("PYTHONSTARTUP");
        String path = environment.remove("JYTHON_CPYTHON_PYTHONPATH");
        if (path != null) {
            environment.put("PYTHONPATH", path);
        }
        return builder;
    }

    private static void verify(File executable) throws IOException, InterruptedException {
        Process check = builder(executable, "-I", "-S", "-c", VERSION_CHECK)
                .redirectErrorStream(true).start();
        Thread shutdownHook = new Thread(() -> terminate(check), "cpython-version-check-shutdown");
        try {
            // The execution hook is not installed yet. Protect the probe as
            // well, including callers using processBuilder directly.
            Runtime.getRuntime().addShutdownHook(shutdownHook);
            check.getOutputStream().close();
            if (!check.waitFor(15, TimeUnit.SECONDS)) {
                throw new IOException("Version check timed out for " + executable);
            }
            String detail;
            try (InputStream input = check.getInputStream();
                    ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[1024];
                int count;
                while (bytes.size() < 4096 && (count = input.read(buffer)) != -1) {
                    bytes.write(buffer, 0, count);
                }
                detail = new String(bytes.toByteArray(), StandardCharsets.UTF_8).trim();
            }
            if (check.exitValue() != 0 || !VERSION_MARKER.equals(detail)) {
                throw new IOException("Requires CPython " + VERSION + " final: "
                        + executable + (detail.isEmpty() ? "" : "\n" + detail));
            }
        } finally {
            try {
                terminate(check);
                check.getInputStream().close();
            } finally {
                try {
                    Runtime.getRuntime().removeShutdownHook(shutdownHook);
                } catch (IllegalStateException ignored) {
                    // JVM shutdown has begun; let the registered hook finish.
                }
            }
        }
    }

    private static void terminate(Process process) {
        if (!process.isAlive()) {
            return;
        }
        process.destroy();
        try {
            if (!process.waitFor(1, TimeUnit.SECONDS)) {
                process.destroyForcibly();
            }
        } catch (InterruptedException error) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
        }
    }
}
