"""Native packaging acceptance: dist/bin/jython3 -B tests/cpython/test_native_extension.py -v.

Requires a POSIX C compiler. Builds only the small trusted C module below.
No downloads, system installation, or third-party build dependencies.
"""
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
import zipfile

SOURCE = r'''
#include <Python.h>
static PyObject *add(PyObject *self, PyObject *args) {
    long left, right;
    if (!PyArg_ParseTuple(args, "ll", &left, &right)) return NULL;
    return PyLong_FromLong(left + right);
}
static PyObject *version(PyObject *self, PyObject *args) {
    return PyUnicode_FromString(PY_VERSION);
}
static PyMethodDef methods[] = {
    {"add", add, METH_VARARGS, "Add two bounded test integers."},
    {"version", version, METH_NOARGS, "Return compilation header version."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_cpython_backend_probe", NULL, -1, methods
};
PyMODINIT_FUNC PyInit__cpython_backend_probe(void) {
    return PyModule_Create(&module);
}
'''


@unittest.skipUnless(os.name == 'posix', 'native test currently supports POSIX compiler flags')
class NativeExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if tuple(sys.version_info) != (3, 15, 2, 'final', 0):
            raise RuntimeError('Run this suite with the actual CPython 3.15.2 backend')
        cls.temporary = tempfile.TemporaryDirectory(prefix='cpython native build ')
        cls.root = Path(cls.temporary.name)
        try:
            compiler = shlex.split(sysconfig.get_config_var('LDSHARED'))
            if not shutil.which(compiler[0]):
                raise RuntimeError('C compiler required: ' + compiler[0])
            source = cls.root / 'probe.c'
            source.write_text(SOURCE)
            cls.extension = cls.root / ('_cpython_backend_probe' + sysconfig.get_config_var('EXT_SUFFIX'))
            command = compiler + shlex.split(sysconfig.get_config_var('CCSHARED') or '')
            command += ['-I' + sysconfig.get_path('include'), str(source), '-o', str(cls.extension)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            spec = importlib.util.spec_from_file_location('_cpython_backend_probe', cls.extension)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)
        except Exception:
            cls.temporary.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_compiled_with_exact_version_headers(self):
        self.assertEqual(self.module.version(), '3.15.2')

    def test_native_function_call(self):
        self.assertEqual(self.module.add(20, 22), 42)
        self.assertEqual(self.module.add(-4, 4), 0)

    def test_native_argument_type_error(self):
        with self.assertRaises(TypeError):
            self.module.add('20', 22)
        with self.assertRaises(TypeError):
            self.module.add(1)

    def test_fresh_process_can_import_extension(self):
        result = subprocess.run([sys.executable, '-B', '-c',
                                 'import _cpython_backend_probe as p; print(p.add(10, 32))'],
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '42')

    def test_native_wheel_offline_install_and_metadata(self):
        tag = 'cp315-cp315-' + sysconfig.get_platform().replace('-', '_').replace('.', '_')
        info = 'cpython_backend_probe-1.0.dist-info/'
        files = {
            self.extension.name: self.extension.read_bytes(),
            info + 'METADATA': (b'Metadata-Version: 2.1\nName: cpython-backend-probe\n'
                                b'Version: 1.0\nRequires-Python: >=3.15\n'),
            info + 'WHEEL': ('Wheel-Version: 1.0\nGenerator: backend-acceptance\n'
                            'Root-Is-Purelib: false\nTag: ' + tag + '\n').encode(),
        }
        record = io.StringIO(newline='')
        writer = csv.writer(record)
        for name, data in files.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
            writer.writerow([name, 'sha256=' + digest, len(data)])
        writer.writerow([info + 'RECORD', '', ''])
        files[info + 'RECORD'] = record.getvalue().encode()
        wheel = self.root / ('cpython_backend_probe-1.0-' + tag + '.whl')
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        environment = self.root / 'venv'
        subprocess.run([sys.executable, '-I', '-m', 'venv', str(environment)],
                       check=True, capture_output=True, timeout=60)
        executable = environment / 'bin/python'
        installed = subprocess.run([str(executable), '-I', '-m', 'pip', '--isolated',
                                    'install', '--no-index', '--no-deps', str(wheel)],
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        result = subprocess.run([str(executable), '-I', '-c',
                                 'import _cpython_backend_probe as p, importlib.metadata as m, json; '
                                 'print(json.dumps([p.add(19, 23), p.version(), '
                                 'm.version("cpython-backend-probe"), p.__file__]))'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        value, version, package_version, location = json.loads(result.stdout)
        self.assertEqual((value, version, package_version), (42, '3.15.2', '1.0'))
        self.assertTrue(Path(location).is_relative_to(environment))


if __name__ == '__main__':
    unittest.main()
