"""Offline installer checks: python3 -B tests/cpython/test_installer.py -v."""
import importlib.util
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('install_cpython', ROOT / 'tools' / 'install_cpython.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def archive(self, directory, name, kind=tarfile.REGTYPE):
        archive = Path(directory) / 'example.tar.xz'
        member = tarfile.TarInfo(name)
        member.type = kind
        member.mode = 0o755
        if kind == tarfile.SYMTYPE:
            member.linkname = '../../outside'
        content = b'example'
        if kind == tarfile.REGTYPE:
            member.size = len(content)
        with tarfile.open(archive, 'w:xz') as bundle:
            bundle.addfile(member, io.BytesIO(content) if member.isfile() else None)
        return archive

    def test_regular_files_and_verified_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory, 'Python-3.15.2/configure')
            work = Path(directory) / 'work'
            source = installer.unpack(archive, work)
            self.assertEqual((source / 'configure').read_bytes(), b'example')
            self.assertEqual(installer.unpack(archive, work), source)

    def test_traversal_and_absolute_paths_rejected(self):
        for name in ('Python-3.15.2/../../outside', '/absolute', 'unexpected/file'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                archive = self.archive(directory, name)
                with self.assertRaisesRegex(RuntimeError, 'Unsafe source archive member'):
                    installer.unpack(archive, Path(directory) / 'work')
                self.assertFalse(Path(directory, 'outside').exists())

    def test_links_and_special_files_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                archive = self.archive(directory, 'Python-3.15.2/link', kind)
                with self.assertRaisesRegex(RuntimeError, 'Unsafe source archive member'):
                    installer.unpack(archive, Path(directory) / 'work')

    def test_invalid_cache_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, installer.ARCHIVE).write_bytes(b'not the pinned source')
            with mock.patch.object(installer.urllib.request, 'urlopen') as request:
                with self.assertRaisesRegex(RuntimeError, 'Checksum mismatch'):
                    installer.download(Path(directory))
                request.assert_not_called()

    def test_unverified_source_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / 'work'
            source = work / 'Python-3.15.2'
            source.mkdir(parents=True)
            (source / 'keep').write_text('user file')
            archive = self.archive(directory, 'Python-3.15.2/configure')
            with self.assertRaisesRegex(RuntimeError, 'Unverified/incomplete source tree'):
                installer.unpack(archive, work)
            self.assertEqual((source / 'keep').read_text(), 'user file')

    def test_environment_cleaning_preserves_build_flags(self):
        with mock.patch.dict(os.environ, {'PYTHONHOME': 'old', 'PYTHONPATH': 'old',
                                         'CPPFLAGS': '-I/example'}, clear=True):
            self.assertEqual(installer.clean_environment(), {'CPPFLAGS': '-I/example'})
            self.assertIn('PYTHONHOME', os.environ)

    def test_verified_download_is_reused_without_network(self):
        content = b'controlled test archive'
        checksum = installer.hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(installer, 'SHA256', checksum), mock.patch.object(
                    installer.urllib.request, 'urlopen', return_value=io.BytesIO(content)) as request:
                path = installer.download(Path(directory))
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(installer.download(Path(directory)), path)
                request.assert_called_once()
                self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_download_checksum_failure_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(installer.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad')):
                with self.assertRaisesRegex(RuntimeError, 'does not match the pin'):
                    installer.download(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_network_failure_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(installer.urllib.request, 'urlopen', side_effect=OSError('offline')):
                with self.assertRaisesRegex(OSError, 'offline'):
                    installer.download(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_partial_download_failure_cleans_temporary_file(self):
        def partial(source, target):
            target.write(b'partial')
            raise OSError('transfer interrupted')
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(installer.urllib.request, 'urlopen', return_value=io.BytesIO()), \
                    mock.patch.object(installer.shutil, 'copyfileobj', side_effect=partial):
                with self.assertRaisesRegex(OSError, 'transfer interrupted'):
                    installer.download(Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_nonempty_prefix_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            keep = Path(directory) / 'keep'
            keep.write_text('original')
            with mock.patch.object(installer.sys, 'argv', ['installer', '--prefix', directory]), \
                    mock.patch.object(installer, 'download') as download, \
                    mock.patch.object(installer.sys, 'stderr', io.StringIO()):
                self.assertEqual(installer.main(), 1)
                download.assert_not_called()
            self.assertEqual(keep.read_text(), 'original')

    def test_existing_runtime_checked_without_reinstall(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'bin/python3.15'
            executable.parent.mkdir()
            executable.touch()
            with mock.patch.object(installer.sys, 'argv', ['installer', '--prefix', directory]), \
                    mock.patch.object(installer, 'check_runtime') as check, \
                    mock.patch.object(installer, 'download') as download:
                self.assertEqual(installer.main(), 0)
                check.assert_called_once_with(executable.resolve())
                download.assert_not_called()

    def test_check_only_never_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(installer.sys, 'argv', ['installer', '--prefix', directory, '--check-only']), \
                    mock.patch.object(installer, 'check_runtime', side_effect=FileNotFoundError()), \
                    mock.patch.object(installer, 'download') as download, \
                    mock.patch.object(installer.sys, 'stderr', io.StringIO()):
                self.assertEqual(installer.main(), 1)
                download.assert_not_called()

    def test_private_install_includes_official_metadata_target(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'runtime'
            source = Path(directory) / 'source'
            with mock.patch.object(installer.sys, 'argv', ['installer', '--prefix', str(prefix), '--jobs', '2']), \
                    mock.patch.object(installer.shutil, 'which', return_value='/usr/bin/make'), \
                    mock.patch.object(installer, 'download', return_value=Path(directory) / 'source.tar.xz'), \
                    mock.patch.object(installer, 'unpack', return_value=source), \
                    mock.patch.object(installer.subprocess, 'run') as run, \
                    mock.patch.object(installer, 'check_runtime') as check:
                self.assertEqual(installer.main(), 0)
                self.assertEqual([call.args[0] for call in run.call_args_list], [
                    [str(source / 'configure'), '--prefix=' + str(prefix), '--with-ensurepip=install'],
                    ['make', '-j2'], ['make', 'install']])
                check.assert_called_once_with(prefix / 'bin/python3.15')


if __name__ == '__main__':
    unittest.main()
