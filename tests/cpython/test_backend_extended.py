"""Extended acceptance: python3 -B tests/cpython/test_backend_extended.py -v.

Requires the JDK (javac) and the built backend. No third-party Python packages.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
import zipapp

import test_backend as base
from test_backend import ROOT, JAVA, EXECUTABLE


class ExtendedTests(unittest.TestCase):
    command = base.BackendTests.command
    run_backend = base.BackendTests.run_backend
    assert_ok = base.BackendTests.assert_ok

    @classmethod
    def setUpClass(cls):
        base.BackendTests.setUpClass()
        if not shutil.which('javac'):
            raise RuntimeError('A JDK is required for Java API acceptance')
        cls.temporary = tempfile.TemporaryDirectory(prefix='cpython java api ')
        cls.classes = Path(cls.temporary.name)
        try:
            subprocess.run(['javac', '-encoding', 'UTF-8', '-source', '8', '-target', '8',
                            '-cp', str(ROOT / 'dist' / 'jython-dev.jar'), '-d', str(cls.classes),
                            str(ROOT / 'tests' / 'cpython' / 'java' / 'CPythonAPIProbe.java')],
                           capture_output=True, check=True, timeout=60)
        except Exception:
            cls.temporary.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def java_api(self, mode, *args, executable=EXECUTABLE):
        result = subprocess.run([JAVA, '-Dpython.cpython.executable=' + str(executable),
                                 '-cp', os.pathsep.join((str(self.classes),
                                                        str(ROOT / 'dist' / 'jython-dev.jar'))),
                                 'CPythonAPIProbe', mode, *map(str, args)],
                                capture_output=True, timeout=60)
        self.assert_ok(result)
        self.assertIn(('API_OK:' + mode).encode(), result.stdout)
        return result

    def test_java_api_binary_pipes(self):
        self.java_api('pipe')

    def test_java_api_custom_cwd_and_environment(self):
        with tempfile.TemporaryDirectory(prefix='cwd 中文 ') as directory:
            self.java_api('cwd', directory)

    def test_java_api_run_does_not_exit_jvm(self):
        self.java_api('run')

    def test_java_api_sixteen_concurrent_builders(self):
        self.java_api('parallel')

    def test_java_api_configuration_refresh(self):
        self.java_api('refresh')

    def test_java_api_invalid_argument(self):
        self.java_api('invalid-argument')

    def assert_pid_gone(self, marker):
        pid = int(marker.read_text())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        # Only the test's explicitly recorded child is eligible for cleanup.
        os.kill(pid, signal.SIGKILL)
        self.fail('test child survived cancellation: %d' % pid)

    @unittest.skipUnless(os.name == 'posix', 'POSIX PID lifecycle')
    def test_java_api_interrupt_running_child(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'pid'
            try:
                self.java_api('interrupt', marker)
            finally:
                if marker.exists() and marker.stat().st_size:
                    self.assert_pid_gone(marker)

    def slow_probe(self, directory):
        marker = Path(directory) / 'pid'
        executable = Path(directory) / 'slow-python'
        executable.write_text('#!' + str(Path(EXECUTABLE).absolute()) + '\n'
                              'import os, pathlib, time\n'
                              'pathlib.Path(' + repr(str(marker)) + ').write_text(str(os.getpid()))\n'
                              'time.sleep(120)\n', encoding='utf-8')
        executable.chmod(0o755)
        return executable, marker

    def stop_jvm_and_check_child(self, command, marker):
        parent = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15
            while (not marker.exists() or marker.stat().st_size == 0) and time.monotonic() < deadline:
                self.assertIsNone(parent.poll(), 'launcher exited before starting child')
                time.sleep(0.025)
            self.assertTrue(marker.exists() and marker.stat().st_size, 'child did not start')
            parent.terminate()
            parent.wait(timeout=10)
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=10)
            parent.stderr.close()
            if marker.exists() and marker.stat().st_size:
                self.assert_pid_gone(marker)

    @unittest.skipUnless(os.name == 'posix', 'POSIX JVM shutdown during version probe')
    def test_jvm_shutdown_during_version_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            executable, marker = self.slow_probe(directory)
            command = self.command(['-V'], properties=['-Dpython.cpython.executable=' + str(executable)])
            self.stop_jvm_and_check_child(command, marker)

    @unittest.skipUnless(os.name == 'posix', 'POSIX TERM handler')
    def test_jvm_shutdown_force_stops_uncooperative_child(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'pid'
            source = ('import os, pathlib, signal, sys, time; '
                      'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                      'pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(120)')
            self.stop_jvm_and_check_child(self.command(['-c', source, str(marker)]), marker)

    @unittest.skipUnless(os.name == 'posix', 'POSIX executable and PID lifecycle')
    def test_java_api_interrupt_version_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            executable, marker = self.slow_probe(directory)
            try:
                self.java_api('interrupt-probe', marker, executable=executable)
            finally:
                if marker.exists() and marker.stat().st_size:
                    self.assert_pid_gone(marker)

    @unittest.skipUnless(os.name == 'posix', 'POSIX executable and PID lifecycle')
    def test_probe_timeout_kills_child(self):
        with tempfile.TemporaryDirectory() as directory:
            executable, marker = self.slow_probe(directory)
            started = time.monotonic()
            try:
                result = self.run_backend(['-V'], properties=[
                    '-Dpython.cpython.executable=' + str(executable)])
                self.assertEqual(result.returncode, 2)
                self.assertIn(b'Version check timed out', result.stderr)
                self.assertLess(time.monotonic() - started, 25)
            finally:
                if marker.exists() and marker.stat().st_size:
                    self.assert_pid_gone(marker)

    def test_four_megabyte_binary_stdin(self):
        data = bytes(range(256)) * 16384
        result = self.run_backend(['-u', '-c', 'import hashlib, sys; '
                                  'print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'], input=data)
        self.assert_ok(result)
        self.assertEqual(result.stdout.strip().decode(), hashlib.sha256(data).hexdigest())

    def test_large_simultaneous_stdout_stderr(self):
        source = ('import sys, threading\n'
                  'def write(stream, char):\n'
                  '    for _ in range(512):\n'
                  '        stream.write(char * 8192)\n'
                  '    stream.flush()\n'
                  'worker = threading.Thread(target=write, args=(sys.stderr.buffer, b"E"))\n'
                  'worker.start()\nwrite(sys.stdout.buffer, b"O")\nworker.join()\n')
        result = self.run_backend(['-u', '-c', source])
        self.assert_ok(result)
        self.assertEqual(result.stdout, b'O' * (4 * 1024 * 1024))
        self.assertEqual(result.stderr, b'E' * (4 * 1024 * 1024))

    def test_parallel_cli_environments_do_not_mix(self):
        def work(index):
            return self.run_backend(['-c', 'import os; print(os.environ["CALL_ID"])'],
                                    env={'CALL_ID': str(index)})
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for index, result in enumerate(pool.map(work, range(12))):
                self.assert_ok(result)
                self.assertEqual(result.stdout.strip(), str(index).encode())

    def test_property_overrides_executable_environment(self):
        result = self.run_backend(['-V'], env={'JYTHON_CPYTHON_EXECUTABLE': '/missing/environment'})
        self.assert_ok(result)
        self.assertIn(b'3.15.2', result.stdout)

    def test_blank_property_rejected(self):
        result = self.run_backend(['-V'], properties=['-Dpython.cpython.executable= '])
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'Empty CPython executable path', result.stderr)

    def test_directory_executable_rejected(self):
        result = self.run_backend(['-V'], properties=['-Dpython.cpython.executable=' + str(ROOT)])
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'not executable', result.stderr)

    def test_default_jar_neighbor_lookup_from_other_directory(self):
        environment = os.environ.copy()
        environment.pop('JYTHON_CPYTHON_EXECUTABLE', None)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([JAVA, '-cp', str(ROOT / 'dist' / 'jython-dev.jar'),
                                     'org.python.util.CPythonLauncher', '-V'],
                                    cwd=directory, env=environment, capture_output=True, timeout=30)
        self.assert_ok(result)
        self.assertIn(b'3.15.2', result.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX shell wrapper')
    def test_shell_via_path_from_other_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, PATH=str(ROOT / 'dist' / 'bin') + os.pathsep + os.environ['PATH'])
            environment.pop('JYTHON_HOME', None)
            result = subprocess.run(['jython3', '-V'], cwd=directory, env=environment,
                                    capture_output=True, timeout=30)
        self.assert_ok(result)
        self.assertIn(b'3.15.2', result.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlinks')
    def test_shell_symlink_from_other_directory(self):
        with tempfile.TemporaryDirectory(prefix='launcher link ') as directory:
            link = Path(directory) / 'python3-jvm'
            link.symlink_to(ROOT / 'dist' / 'bin' / 'jython3')
            environment = os.environ.copy()
            environment.pop('JYTHON_HOME', None)
            result = subprocess.run([str(link), '-V'], cwd=directory, env=environment,
                                    capture_output=True, timeout=30)
        self.assert_ok(result)
        self.assertIn(b'3.15.2', result.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlinks')
    def test_shell_relative_symlink_chain(self):
        with tempfile.TemporaryDirectory(prefix='relative 中文 ') as directory:
            root = Path(directory)
            (root / 'first').symlink_to('second')
            (root / 'second').symlink_to(os.path.relpath(ROOT / 'dist/bin/jython3', root))
            environment = os.environ.copy()
            environment.pop('JYTHON_HOME', None)
            result = subprocess.run([str(root / 'first'), '-V'], cwd=root, env=environment,
                                    capture_output=True, timeout=30)
        self.assert_ok(result)
        self.assertIn(b'3.15.2', result.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX shell wrapper')
    def test_explicit_invalid_home_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(ROOT / 'dist/bin/jython3'), '-V'],
                                    env=dict(os.environ, JYTHON_HOME=directory),
                                    capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'Cannot find Jython JAR', result.stderr)

    def test_utf8_under_c_locale(self):
        result = self.run_backend(['-c', 'import json, sys; print(json.dumps(['
                                  'sys.getdefaultencoding(), sys.getfilesystemencoding(), '
                                  'sys.stdout.encoding]))'], env={'LC_ALL': 'C', 'LANG': 'C'})
        self.assert_ok(result)
        self.assertEqual(json.loads(result.stdout), ['utf-8', 'utf-8', 'utf-8'])

    def test_isolated_mode_ignores_namespaced_pythonpath(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_backend(['-I', '-c', 'import json, sys; print(json.dumps(sys.path))'],
                                      env={'JYTHON_CPYTHON_PYTHONPATH': directory})
            self.assert_ok(result)
            self.assertNotIn(directory, json.loads(result.stdout))

    def test_zipapp_with_unicode_argument(self):
        with tempfile.TemporaryDirectory(prefix='zip app ') as directory:
            source = Path(directory) / 'source'
            source.mkdir()
            (source / '__main__.py').write_text('import json, sys\nprint(json.dumps(sys.argv[1:]))\n')
            archive = Path(directory) / 'application.pyz'
            zipapp.create_archive(source, archive)
            result = self.run_backend([str(archive), '中文 value'])
            self.assert_ok(result)
            self.assertEqual(json.loads(result.stdout), ['中文 value'])

    def test_package_relative_import(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'app'
            package.mkdir()
            (package / '__init__.py').write_text('')
            (package / 'values.py').write_text('answer = 42\n')
            (package / '__main__.py').write_text('from .values import answer\nprint(answer)\n')
            result = self.run_backend(['-m', 'app'], cwd=directory)
            self.assert_ok(result)
            self.assertEqual(result.stdout.strip(), b'42')


if __name__ == '__main__':
    unittest.main()
