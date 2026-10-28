"""Run with host Python 3.9+: python3 -B tests/cpython/test_backend.py -v."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE = os.environ.get('JYTHON_CPYTHON_EXECUTABLE', str(
    ROOT / 'dist' / 'cpython' / ('python.exe' if os.name == 'nt' else 'bin/python3.15')))
CLASSPATH = os.environ.get('JYTHON_TEST_CLASSPATH', os.pathsep.join((
    str(ROOT / 'dist' / 'jython-dev.jar'), str(ROOT / 'extlibs' / '*'))))
JAVA = shutil.which('java')


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if JAVA is None or not Path(EXECUTABLE).is_file():
            raise RuntimeError('Build Jython and install CPython 3.15.2 before running these tests')

    def command(self, args, properties=(), main='CPythonLauncher'):
        return [JAVA, '-Dpython.home=' + str(ROOT / 'dist'),
                '-Dpython.cpython.executable=' + EXECUTABLE, *properties,
                '-cp', CLASSPATH, 'org.python.util.' + main, *args]

    def run_backend(self, args, *, properties=(), main='CPythonLauncher',
                    env=None, cwd=None, input=None):
        environment = os.environ.copy()
        if env:
            environment.update(env)
        return subprocess.run(self.command(args, properties, main), input=input,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=environment, cwd=cwd or ROOT, timeout=60)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))

    def test_exact_runtime_and_standard_library(self):
        result = self.run_backend(['-c', 'import sys, json, pathlib; '
                                  'print(json.dumps([sys.implementation.name, list(sys.version_info), '
                                  'str(pathlib.__file__), sys.base_prefix]))'])
        self.assert_ok(result)
        name, version, path, base_prefix = json.loads(result.stdout)
        self.assertEqual(name, 'cpython')
        self.assertEqual(version, [3, 15, 2, 'final', 0])
        self.assertTrue(Path(path).resolve().is_relative_to(Path(base_prefix).resolve()))
        self.assertNotIn('lib-python/2.7', path)

    def test_legacy_entry_opt_in(self):
        result = self.run_backend(['-V'], properties=['-Dpython.runtime=cpython'], main='jython')
        self.assert_ok(result)
        self.assertIn(b'Python 3.15.2', result.stdout)

    def test_legacy_entry_unchanged(self):
        result = self.run_backend(['-V'], main='jython')
        self.assert_ok(result)
        self.assertIn(b'Jython 2.7.', result.stderr)

    def test_unknown_runtime_rejected(self):
        result = self.run_backend(['-c', 'print("must not execute")'],
                                  properties=['-Dpython.runtime=unknown'], main='jython')
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'Unknown python.runtime', result.stderr)
        self.assertEqual(result.stdout, b'')

    def test_literal_arguments(self):
        values = ['with spaces', '中文', '"quotes"', '$HOME; echo INJECTION', '--runtime=other']
        result = self.run_backend(['-c', 'import json, sys; print(json.dumps(sys.argv[1:]))', *values])
        self.assert_ok(result)
        self.assertEqual(json.loads(result.stdout), values)

    def test_binary_stdin_stdout(self):
        payload = b'\x00\xff\n' + '中文'.encode()
        result = self.run_backend(['-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],
                                  input=payload)
        self.assert_ok(result)
        self.assertEqual(result.stdout, payload)

    def test_stdin_program(self):
        result = self.run_backend(['-'], input=b'print(6 * 7)\n')
        self.assert_ok(result)
        self.assertEqual(result.stdout.strip(), b'42')

    def test_exit_status_and_stderr(self):
        result = self.run_backend(['-c', 'import sys; print("error", file=sys.stderr); sys.exit(7)'])
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stderr.strip(), b'error')

    def test_syntax_error(self):
        result = self.run_backend(['-c', 'def invalid('])
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'SyntaxError', result.stderr)

    def test_file_module_and_working_directory(self):
        with tempfile.TemporaryDirectory(prefix='cpython backend ') as directory:
            path = Path(directory) / 'example.py'
            path.write_text('import os, sys, json\nprint(json.dumps([os.getcwd(), sys.argv[1:]]))\n')
            for args in ([str(path), 'a b'], ['-m', 'example', 'a b']):
                result = self.run_backend(args, cwd=directory)
                self.assert_ok(result)
                self.assertEqual(json.loads(result.stdout), [directory, ['a b']])

    def test_legacy_python_environment_is_not_inherited(self):
        result = self.run_backend(['-c', 'import csv, io, json, sys; print(json.dumps(sys.path))'], env={
            'PYTHONHOME': '/missing-legacy-python-home',
            'PYTHONPATH': str(ROOT / 'Lib'),
            'PYTHONSTARTUP': '/missing-legacy-startup.py',
            'JYTHONPATH': str(ROOT / 'lib-python' / '2.7'),
        })
        self.assert_ok(result)
        self.assertNotIn(str(ROOT / 'Lib'), json.loads(result.stdout))
        self.assertNotIn(str(ROOT / 'lib-python' / '2.7'), json.loads(result.stdout))

    def test_explicit_cpython_path(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'backend_example.py').write_text('value = 42\n')
            result = self.run_backend(['-c', 'import backend_example; print(backend_example.value)'],
                                      env={'JYTHON_CPYTHON_PYTHONPATH': directory})
            self.assert_ok(result)
            self.assertEqual(result.stdout.strip(), b'42')

    def test_missing_executable_no_fallback(self):
        result = self.run_backend(['-c', 'print("must not execute")'],
                                  properties=['-Dpython.cpython.executable=/not/a/python/executable'])
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'Executable not found', result.stderr)
        self.assertEqual(result.stdout, b'')

    @unittest.skipIf(sys.version_info[:3] == (3, 15, 2), 'host is the target version')
    def test_wrong_version_no_fallback(self):
        result = self.run_backend(['-c', 'print("must not execute")'],
                                  properties=['-Dpython.cpython.executable=' + sys.executable])
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'Requires CPython 3.15.2 final', result.stderr)
        self.assertEqual(result.stdout, b'')

    @unittest.skipUnless(os.name == 'posix', 'POSIX executable script')
    def test_zero_exit_without_version_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'not-python'
            fake.write_text('#!/bin/sh\nexit 0\n')
            fake.chmod(0o755)
            result = self.run_backend(['-V'],
                                      properties=['-Dpython.cpython.executable=' + str(fake)])
            self.assertEqual(result.returncode, 2)
            self.assertIn(b'Requires CPython 3.15.2 final', result.stderr)

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlink')
    def test_executable_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='python path ') as directory:
            executable = Path(directory) / 'python with spaces'
            executable.symlink_to(Path(EXECUTABLE).absolute())
            result = self.run_backend(['-V'],
                                      properties=['-Dpython.cpython.executable=' + str(executable)])
            self.assert_ok(result)
            self.assertIn(b'Python 3.15.2', result.stdout)

    def test_executable_environment_setting(self):
        command = [item for item in self.command(['-V'])
                   if not item.startswith('-Dpython.cpython.executable=')]
        result = subprocess.run(command, capture_output=True, timeout=30,
                                env=dict(os.environ, JYTHON_CPYTHON_EXECUTABLE=EXECUTABLE))
        self.assert_ok(result)
        self.assertIn(b'Python 3.15.2', result.stdout)

    def test_original_stdlib_examples(self):
        result = self.run_backend(['-B', str(ROOT / 'Demo' / 'python3_stdlib_smoke.py')])
        self.assert_ok(result)
        self.assertIn(b'16 passed, 0 failed', result.stdout)

    def test_venv_and_pip_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            venv = Path(directory) / 'venv'
            result = self.run_backend(['-m', 'venv', str(venv)])
            self.assert_ok(result)
            executable = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            result = self.run_backend(['-m', 'pip', '--version'],
                                      properties=['-Dpython.cpython.executable=' + str(executable)])
            self.assert_ok(result)
            self.assertIn(b'python 3.15', result.stdout)
            self.assertIn(str(venv).encode(), result.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX shutdown and shell launcher')
    def test_shell_launcher(self):
        result = subprocess.run([str(ROOT / 'dist' / 'bin' / 'jython3'), '-V'],
                                env=dict(os.environ, JYTHON_CPYTHON_EXECUTABLE=EXECUTABLE),
                                capture_output=True, timeout=30)
        self.assert_ok(result)
        self.assertIn(b'Python 3.15.2', result.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX process termination')
    def test_jvm_shutdown_stops_child(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'pid'
            source = ('import os, pathlib, time; pathlib.Path(' + repr(str(marker))
                      + ').write_text(str(os.getpid())); time.sleep(120)')
            parent = subprocess.Popen(self.command(['-c', source]),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            child_pid = None
            try:
                deadline = time.monotonic() + 20
                while not marker.exists() and time.monotonic() < deadline:
                    if parent.poll() is not None:
                        self.fail(parent.stderr.read().decode())
                    time.sleep(0.05)
                self.assertTrue(marker.exists(), 'child did not start')
                child_pid = int(marker.read_text())
                parent.terminate()
                parent.wait(timeout=10)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)
                child_pid = None
            finally:
                if parent.poll() is None:
                    parent.kill()
                    parent.wait(timeout=10)
                parent.stderr.close()
                if child_pid is not None:
                    try:
                        os.kill(child_pid, 9)
                    except ProcessLookupError:
                        pass


if __name__ == '__main__':
    unittest.main()
