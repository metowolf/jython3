"""Filesystem distribution metadata for the JVM standard library.

Supports dist-info, egg-info directories and single-file egg-info on sys.path.
This initial port does not provide entry-point discovery or zip distributions.
"""
from __future__ import unicode_literals

from email.message import Message
import io
import os
import re
import sys

__all__ = ['PackageNotFoundError', 'Distribution', 'distribution',
           'distributions', 'metadata', 'version', 'requires']


class PackageNotFoundError(ImportError):
    """No installed distribution has the requested normalized name."""


def _normalize(name):
    if not isinstance(name, basestring) or not name:
        raise ValueError('A distribution name is required')
    return re.sub(r'[-_.]+', '-', name).lower()


class Distribution(object):
    def __init__(self, path):
        self._path = path

    @classmethod
    def from_name(cls, name):
        normalized = _normalize(name)
        for candidate in distributions():
            candidate_name = candidate.metadata.get('Name')
            if candidate_name and _normalize(candidate_name) == normalized:
                return candidate
        raise PackageNotFoundError(name)

    @classmethod
    def discover(cls, **kwargs):
        return distributions(**kwargs)

    def read_text(self, filename):
        if os.path.isfile(self._path):
            if filename not in ('METADATA', 'PKG-INFO'):
                return None
            path = self._path
        else:
            path = os.path.join(self._path, filename)
        try:
            with io.open(path, encoding='utf-8') as stream:
                return stream.read()
        except (IOError, OSError):
            return None

    @property
    def metadata(self):
        text = self.read_text('METADATA')
        if text is None:
            text = self.read_text('PKG-INFO')
        result = Message()
        header, separator, body = (text or '').partition('\n\n')
        key = None
        value = []
        for line in header.splitlines():
            if line.startswith((' ', '\t')) and key is not None:
                value.append(line.strip())
                continue
            if key is not None:
                result[key] = ' '.join(value)
            key, colon, rest = line.partition(':')
            key = key if colon else None
            value = [rest.strip()]
        if key is not None:
            result[key] = ' '.join(value)
        result.set_payload(body)
        return result

    @property
    def version(self):
        return self.metadata.get('Version')

    @property
    def requires(self):
        return self.metadata.get_all('Requires-Dist')


def distributions(path=None, name=None):
    normalized = _normalize(name) if name is not None else None
    seen = set()
    for directory in sys.path if path is None else path:
        if not isinstance(directory, basestring):
            continue
        directory = os.path.abspath(directory or os.curdir)
        if directory in seen:
            continue
        seen.add(directory)
        try:
            names = sorted(os.listdir(directory))
        except (IOError, OSError):
            continue
        for entry in names:
            if entry.endswith(('.dist-info', '.egg-info')):
                candidate = Distribution(os.path.join(directory, entry))
                candidate_name = candidate.metadata.get('Name')
                if candidate_name and (normalized is None or _normalize(candidate_name) == normalized):
                    yield candidate


def distribution(name):
    return Distribution.from_name(name)


def metadata(name):
    return distribution(name).metadata


def version(name):
    return distribution(name).version


def requires(name):
    return distribution(name).requires
