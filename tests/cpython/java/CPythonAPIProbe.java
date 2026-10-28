import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.python.util.CPythonLauncher;

/** Integration-only program; compile and run with test_backend_extended.py. */
public final class CPythonAPIProbe {
    private static void require(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    private static byte[] readBytes(InputStream input) throws IOException {
        try (InputStream stream = input; ByteArrayOutputStream result = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                result.write(buffer, 0, count);
            }
            return result.toByteArray();
        }
    }

    private static String read(InputStream input) throws IOException {
        return new String(readBytes(input), StandardCharsets.UTF_8);
    }

    private static String capture(ProcessBuilder builder) throws Exception {
        Process child = builder.redirectErrorStream(true).start();
        try {
            child.getOutputStream().close();
            String output = read(child.getInputStream());
            require(child.waitFor(10, TimeUnit.SECONDS), "child did not exit");
            require(child.exitValue() == 0, output);
            return output.trim();
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(10, TimeUnit.SECONDS);
            }
        }
    }

    private static void pipe() throws Exception {
        Process child = CPythonLauncher.processBuilder("-u", "-c", "import sys; "
                + "data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data[::-1]); "
                + "sys.stderr.write('separate stderr')").start();
        byte[] data = "Java to Python: 中文".getBytes(StandardCharsets.UTF_8);
        try {
            try (OutputStream input = child.getOutputStream()) {
                input.write(data);
            }
            byte[] reversed = readBytes(child.getInputStream());
            byte[] expected = new byte[data.length];
            for (int i = 0; i < data.length; i++) {
                expected[i] = data[data.length - i - 1];
            }
            require(Arrays.equals(reversed, expected), "binary response corrupted");
            require("separate stderr".equals(read(child.getErrorStream())), "stderr not separate");
            require(child.waitFor(10, TimeUnit.SECONDS) && child.exitValue() == 0, "pipe exit");
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(10, TimeUnit.SECONDS);
            }
        }
        require("fedcba".equals(capture(CPythonLauncher.processBuilder("-c",
                "print('abcdef'[::-1])"))), "incorrect response");
    }

    private static void parallel() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<String>> results = new ArrayList<>();
            for (int i = 0; i < 16; i++) {
                final int value = i;
                results.add(pool.submit(() -> capture(CPythonLauncher.processBuilder(
                        "-c", "import sys; print(int(sys.argv[1]) ** 2)", Integer.toString(value)))));
            }
            for (int i = 0; i < results.size(); i++) {
                require(Integer.toString(i * i).equals(results.get(i).get(30, TimeUnit.SECONDS)),
                        "concurrent output mixed");
            }
        } finally {
            pool.shutdownNow();
            require(pool.awaitTermination(10, TimeUnit.SECONDS), "executor did not stop");
        }
    }

    private static void interrupt(Path marker, boolean probing) throws Exception {
        AtomicInteger status = new AtomicInteger(-1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread worker = new Thread(() -> {
            try {
                status.set(CPythonLauncher.run("-c", "import os, pathlib, sys, time; "
                        + "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(120)",
                        marker.toString()));
                require(Thread.currentThread().isInterrupted(), "interrupt flag not restored");
            } catch (Throwable error) {
                failure.set(error);
            }
        });
        worker.start();
        try {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
            while ((!Files.exists(marker) || Files.size(marker) == 0) && System.nanoTime() < deadline) {
                Thread.sleep(20);
            }
            require(Files.exists(marker) && Files.size(marker) > 0,
                    probing ? "probe did not start" : "execution did not start");
        } finally {
            worker.interrupt();
            worker.join(10000);
        }
        require(!worker.isAlive(), "interrupted launcher blocked");
        require(failure.get() == null, "worker exception: " + failure.get());
        require(status.get() == 130, "interrupted exit must be 130: " + status.get());
    }

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        switch (mode) {
            case "pipe":
                pipe();
                break;
            case "cwd":
                ProcessBuilder builder = CPythonLauncher.processBuilder("-c",
                        "import os; print(os.getcwd()); print(os.environ['API_ONLY'])");
                builder.directory(new File(args[1]));
                builder.environment().put("API_ONLY", "custom-environment");
                String[] lines = capture(builder).split("\\R");
                require(new File(lines[0]).getCanonicalFile().equals(new File(args[1]).getCanonicalFile()),
                        "working directory not applied");
                require(lines[1].equals("custom-environment"), "builder environment not applied");
                break;
            case "run":
                require(CPythonLauncher.run("-c", "import sys; sys.exit(9)") == 9,
                        "run did not preserve exit code");
                require(CPythonLauncher.run("-c", "pass") == 0, "subsequent run failed");
                break;
            case "parallel":
                parallel();
                break;
            case "interrupt":
            case "interrupt-probe":
                interrupt(Paths.get(args[1]), mode.equals("interrupt-probe"));
                break;
            case "refresh":
                String original = System.getProperty(CPythonLauncher.EXECUTABLE_PROPERTY);
                require("42".equals(capture(CPythonLauncher.processBuilder("-c", "print(42)"))), "first call");
                System.setProperty(CPythonLauncher.EXECUTABLE_PROPERTY, "/missing/configuration");
                try {
                    CPythonLauncher.processBuilder("-V");
                    throw new AssertionError("stale executable was cached");
                } catch (IOException expected) {
                    require(expected.getMessage().contains("Executable not found"), expected.toString());
                } finally {
                    System.setProperty(CPythonLauncher.EXECUTABLE_PROPERTY, original);
                }
                require("43".equals(capture(CPythonLauncher.processBuilder("-c", "print(43)"))), "recovery");
                break;
            case "invalid-argument":
                require(CPythonLauncher.run("-c", "\u0000") == 2, "invalid argument not rejected");
                break;
            default:
                throw new IllegalArgumentException(mode);
        }
        System.out.println("API_OK:" + mode);
    }
}