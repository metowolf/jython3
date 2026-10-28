#!/usr/bin/env python3
"""Build a private CPython 3.15.2 on POSIX using Python 3.9+ and a C toolchain.

No sudo, system package installation, shell commands, or third-party Python
packages are used. Install the native development dependencies first; see
Doc/cpython-backend.md. Outputs default to the ignored build/ and dist/ trees.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

VERSION = "3.15.2"
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "Python-" + VERSION + ".tar.xz"
URL = "https://www.python.org/ftp/python/" + VERSION + "/" + ARCHIVE
# SHA2_256 messageDigest published at URL + '.sigstore'. The pinned digest is
# checked locally; this script does not claim to verify a Sigstore signature.
SHA256 = "8b5536d280142ecf6cdfe15d12a21ba1c65e300bbf7b28a8d0cdb849575797de"
CHECK = r'''
import importlib
import sys
if (sys.implementation.name != 'cpython' or
        tuple(sys.version_info) != (3, 15, 2, 'final', 0)):
    raise SystemExit('Expected CPython 3.15.2 final, got ' + sys.version)
required = ('_decimal', 'asyncio', 'bz2', 'compression.zstd', 'ctypes', 'csv', 'dataclasses',
            'dbm.sqlite3', 'decimal', 'ensurepip', 'hashlib', 'importlib.metadata',
            'importlib.resources', 'json', 'lzma', 'multiprocessing', 'pathlib',
            'readline', 'socket', 'sqlite3', 'ssl', 'tomllib', 'typing', 'venv',
            'zoneinfo', 'zlib')
failed = []
for name in required:
    try:
        importlib.import_module(name)
    except Exception as error:
        failed.append('%s: %s' % (name, error))
if failed:
    raise SystemExit('Missing required standard-library support:\n' + '\n'.join(failed))
import json
import sysconfig
from pathlib import Path
metadata_path = Path(sysconfig.get_path('stdlib')) / 'build-details.json'
if not metadata_path.is_file():
    raise SystemExit('Missing ' + str(metadata_path) + '; use make install in the private build tree, not altinstall')
metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
expected = dict(zip(('major', 'minor', 'micro', 'releaselevel', 'serial'), sys.version_info))
if (metadata.get('implementation', {}).get('name') != 'cpython'
        or metadata.get('language', {}).get('version_info') != expected):
    raise SystemExit('Build metadata does not match the installed CPython version')
print(sys.version)
print('Required standard-library imports: %d passed' % len(required))
print('Build metadata: ' + str(metadata_path))
print('Executable: ' + sys.executable)
'''


def clean_environment():
    environment = os.environ.copy()
    for name in list(environment):
        if name.startswith('PYTHON'):
            environment.pop(name)
    return environment


def check_runtime(executable):
    subprocess.run([str(executable), '-I', '-B', '-c', CHECK],
                   env=clean_environment(), check=True, timeout=60)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def download(cache):
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / ARCHIVE
    if archive.exists():
        if digest(archive) != SHA256:
            raise RuntimeError('Checksum mismatch: ' + str(archive)
                               + '; remove the invalid cache file and retry')
        return archive
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=str(cache), delete=False) as target:
            temporary = Path(target.name)
            print('Downloading ' + URL, flush=True)
            with urllib.request.urlopen(URL, timeout=60) as response:
                shutil.copyfileobj(response, target)
        if digest(temporary) != SHA256:
            raise RuntimeError('Downloaded CPython source checksum does not match the pin')
        temporary.replace(archive)
        return archive
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def unpack(archive, work):
    work.mkdir(parents=True, exist_ok=True)
    source = work / ('Python-' + VERSION)
    marker = source / '.jython-source-sha256'
    if source.exists():
        if marker.is_file() and marker.read_text().strip() == SHA256:
            return source
        raise RuntimeError('Unverified/incomplete source tree: ' + str(source)
                           + '; use a new --work-dir')
    # The pinned official archive contains only regular files and directories.
    # Extract manually rather than trusting tar paths, links, or special files.
    with tarfile.open(archive, 'r:xz') as bundle:
        members = bundle.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if (not parts or parts[0] != source.name or '..' in parts
                    or Path(member.name).is_absolute()
                    or not (member.isdir() or member.isfile())):
                raise RuntimeError('Unsafe source archive member: ' + member.name)
        for member in members:
            target = work / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as original, target.open('xb') as output:
                    shutil.copyfileobj(original, output)
                target.chmod(member.mode & 0o755)
    marker.write_text(SHA256 + '\n')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=ROOT / 'dist' / 'cpython')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / 'build' / 'cpython-downloads')
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'build' / ('cpython-' + VERSION))
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 1, 4))
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('source installation is POSIX-only; configure an official 3.15.2 executable on Windows')
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    prefix = args.prefix.resolve()
    executable = prefix / 'bin' / 'python3.15'
    try:
        if args.check_only or executable.exists():
            check_runtime(executable)
            return 0
        if prefix.exists() and any(prefix.iterdir()):
            raise RuntimeError('Refusing to overwrite non-empty prefix: ' + str(prefix))
        if not shutil.which('make'):
            raise RuntimeError('make is required; see Doc/cpython-backend.md')
        archive = download(args.cache_dir.resolve())
        source = unpack(archive, args.work_dir.resolve())
        environment = clean_environment()
        commands = [
            [str(source / 'configure'), '--prefix=' + str(prefix), '--with-ensurepip=install'],
            ['make', '-j' + str(args.jobs)],
            # The private prefix cannot affect system executables. Unlike
            # altinstall, install also copies CPython's build-details.json.
            ['make', 'install'],
        ]
        for command in commands:
            print('Running: ' + repr(command), flush=True)
            subprocess.run(command, cwd=str(source), env=environment, check=True)
        check_runtime(executable)
        print('Private CPython installed. Build Jython, then use dist/bin/jython3.')
        if prefix != (ROOT / 'dist' / 'cpython').resolve():
            print('Set JYTHON_CPYTHON_EXECUTABLE=' + str(executable))
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print('CPython installation failed: ' + str(error), file=sys.stderr)
        print('See Doc/cpython-backend.md for native dependencies and recovery.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
