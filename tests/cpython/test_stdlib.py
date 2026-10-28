"""Run via dist/bin/jython3 -B tests/cpython/test_stdlib.py -v.

These are targeted acceptance tests, not the full CPython regression suite.
No network servers or third-party packages are required.
"""
import asyncio
import contextlib
import io
import json
import multiprocessing
import sys
import unittest


def child_worker(queue):
    queue.put((sys.implementation.name, tuple(sys.version_info)))


class StandardLibraryTests(unittest.TestCase):
    def test_exact_runtime(self):
        self.assertEqual(sys.implementation.name, 'cpython')
        self.assertEqual(tuple(sys.version_info), (3, 15, 2, 'final', 0))
        self.assertEqual(sys.hexversion, 0x030f02f0)

    def test_build_metadata_installed(self):
        import sysconfig
        from pathlib import Path
        data = json.loads(Path(sysconfig.get_path('stdlib'), 'build-details.json').read_text())
        self.assertEqual(data['implementation']['name'], 'cpython')
        self.assertEqual(data['language']['version_info']['micro'], 2)
        self.assertEqual(data['language']['version_info']['minor'], 15)
        self.assertTrue(Path(data['base_interpreter']).is_file())
        self.assertTrue(Path(data['c_api']['headers'], 'Python.h').is_file())

    @unittest.skipUnless(sys.platform != 'win32', 'POSIX paths')
    def test_realpath_missing_parent_and_embedded_null(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            missing = os.path.join(directory, 'guaranteed-missing', 'x\x00')
            self.assertFalse(os.path.exists(os.path.dirname(missing)))
            for path in (missing, os.fsencode(missing)):
                for strict in (True, os.path.ALL_BUT_LAST):
                    with self.subTest(path=path, strict=strict):
                        with self.assertRaises(FileNotFoundError):
                            os.path.realpath(path, strict=strict)
                for strict in (False, os.path.ALLOW_MISSING):
                    with self.subTest(path=path, strict=strict):
                        with self.assertRaises(ValueError):
                            os.path.realpath(path, strict=strict)

    def test_python3_core_semantics(self):
        self.assertIsInstance('中文', str)
        self.assertNotIsInstance(b'bytes', str)
        self.assertEqual('中文'.encode().decode(), '中文')
        self.assertEqual(3 / 2, 1.5)
        self.assertEqual(list(range(3)), [0, 1, 2])
        mapping = {'b': 1, 'a': 2}
        keys = mapping.keys()
        mapping['c'] = 3
        self.assertEqual(list(keys), ['b', 'a', 'c'])

    def test_csv_text_io(self):
        import csv
        stream = io.StringIO(newline='')
        rows = [['中文', 'a,b'], ['line\nbreak', '42']]
        csv.writer(stream).writerows(rows)
        stream.seek(0)
        self.assertEqual(list(csv.reader(stream)), rows)

    def test_async_task_group(self):
        async def run():
            async with asyncio.TaskGroup() as group:
                first = group.create_task(asyncio.sleep(0, result=21))
                second = group.create_task(asyncio.sleep(0, result=21))
            return first.result() + second.result()
        self.assertEqual(asyncio.run(run()), 42)

    def test_sqlite_transactions(self):
        import sqlite3
        with contextlib.closing(sqlite3.connect(':memory:', autocommit=False)) as connection:
            connection.execute('CREATE TABLE items (name TEXT)')
            connection.commit()
            connection.execute('INSERT INTO items VALUES (?)', ('中文',))
            connection.commit()
            self.assertEqual(connection.execute('SELECT name FROM items').fetchone(), ('中文',))
            connection.execute('DELETE FROM items')
            connection.rollback()
            self.assertEqual(connection.execute('SELECT count(*) FROM items').fetchone(), (1,))

    def test_ssl_context(self):
        import ssl
        context = ssl.create_default_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertTrue(context.get_ciphers())

    def test_compression_extensions(self):
        import bz2
        import lzma
        import zlib
        from compression import zstd
        data = 'Python 3.15.2 中文'.encode() * 20
        for module in (bz2, lzma, zlib, zstd):
            with self.subTest(module=module.__name__):
                self.assertEqual(module.decompress(module.compress(data)), data)

    def test_decimal_accelerator(self):
        import _decimal
        import decimal
        self.assertIs(decimal.Decimal, _decimal.Decimal)
        self.assertEqual(decimal.Decimal('0.1') + decimal.Decimal('0.2'), decimal.Decimal('0.3'))

    def test_ctypes(self):
        import ctypes
        number = ctypes.c_int(42)
        self.assertEqual(ctypes.pointer(number).contents.value, 42)
        self.assertGreater(ctypes.sizeof(ctypes.c_void_p), 0)

    def test_timezone(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        self.assertEqual(datetime(2026, 10, 28, tzinfo=ZoneInfo('UTC')).utcoffset(), timedelta(0))

    def test_dataclass_and_typing(self):
        from dataclasses import asdict, dataclass
        from typing import get_type_hints
        @dataclass
        class Item:
            name: str
            tags: list[str]
        self.assertEqual(asdict(Item('demo', ['x'])), {'name': 'demo', 'tags': ['x']})
        self.assertEqual(get_type_hints(Item)['tags'], list[str])

    def test_deferred_annotations(self):
        namespace = {}
        exec('def identity(x: DefinedLater) -> DefinedLater:\n    return x\n'
             'class DefinedLater:\n    pass\n', namespace)
        self.assertIs(namespace['identity'].__annotations__['x'], namespace['DefinedLater'])

    def test_tomllib(self):
        import tomllib
        self.assertEqual(tomllib.loads('[tool]\nversion = "3.15.2"')['tool']['version'], '3.15.2')

    def test_exception_group(self):
        caught = []
        try:
            raise ExceptionGroup('example', [ValueError('first'), TypeError('second')])
        except* ValueError as error:
            caught.extend(type(item) for item in error.exceptions)
        except* TypeError as error:
            caught.extend(type(item) for item in error.exceptions)
        self.assertEqual(caught, [ValueError, TypeError])

    def test_pattern_matching(self):
        match {'kind': 'task', 'value': 42}:
            case {'kind': 'task', 'value': value}:
                self.assertEqual(value, 42)
            case _:
                self.fail('pattern did not match')

    def test_python315_unpacking(self):
        values = [[1, 2], [3, 4]]
        self.assertEqual([*items for items in values], [1, 2, 3, 4])
        self.assertEqual({**item for item in [{'a': 1}, {'b': 2}]}, {'a': 1, 'b': 2})

    def test_python315_builtins(self):
        immutable = frozendict(a=1, b=2)
        self.assertEqual(json.loads(json.dumps(immutable)), {'a': 1, 'b': 2})
        self.assertEqual(hash(immutable), hash(frozendict(b=2, a=1)))
        with self.assertRaises(TypeError):
            immutable['c'] = 3
        import copy
        missing = sentinel('MISSING')
        self.assertIs(copy.copy(missing), missing)

    def test_template_strings(self):
        from string.templatelib import Template
        value = 42
        template = t'value={value}'
        self.assertIsInstance(template, Template)
        self.assertEqual(template.values, (42,))

    def test_lazy_import(self):
        namespace = {}
        exec('lazy import fractions\nresult = fractions.Fraction(1, 2)\n', namespace)
        self.assertEqual(float(namespace['result']), 0.5)

    def test_socket_pair(self):
        import socket
        left, right = socket.socketpair()
        with left, right:
            left.settimeout(5)
            right.settimeout(5)
            left.sendall(b'hello')
            self.assertEqual(right.recv(5), b'hello')

    def test_multiprocessing_spawn(self):
        context = multiprocessing.get_context('spawn')
        queue = context.Queue()
        process = context.Process(target=child_worker, args=(queue,))
        try:
            process.start()
            self.assertEqual(queue.get(timeout=15), ('cpython', (3, 15, 2, 'final', 0)))
            process.join(timeout=15)
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            process.close()
            queue.close()
            queue.join_thread()


if __name__ == '__main__':
    unittest.main()
