# Bundled standard-library ports

These modules are part of Jython's library migration. They do not replace or
patch the Drain3, cachetools, jsonpickle, GeoIP2 or maxminddb application sources.
Original license texts are retained here and applicable notices remain in sources.

| Installed source | Upstream source | Local changes | License text |
| --- | --- | --- | --- |
| `Lib/typing.py` | PyPI typing 3.7.4.3, Python 2 backport | Added `Collection` using the migrated collections ABC | `typing-3.7.4.3.dist-info-LICENSE` |
| `Lib/six.py` | PyPI six 1.16.0 | None | `six-1.16.0.dist-info-LICENSE` |
| `Lib/configparser.py`, `Lib/backports/configparser/` | PyPI configparser 4.0.2 | Bundled backport package layout | `configparser-4.0.2.dist-info-LICENSE` |
| `Lib/pathlib.py` | PyPI pathlib2 2.1.0, `pathlib2.py` | Installed under the standard-library name | `pathlib2-2.1.0-LICENSE.rst` |
| `Lib/dataclasses.py` | PyPI dataclasses 0.8 | Legacy-compatible syntax, native read-only mapping proxy, ordered field tables, `type` class factory, repr/docstring fallbacks, keyword-only fields and Unicode annotation recognition | `dataclasses-0.8-LICENSE` |
| `Lib/abc.py` | Repository `lib-python/2.7/abc.py` | Added `ABC` | `PSF.txt` and repository license |
| `Lib/collections/__init__.py` | Repository `lib-python/2.7/collections.py` | Package layout and `OrderedDict.move_to_end` | `PSF.txt` and repository license |
| `Lib/collections/abc.py` | Repository `Lib/_abcoll.py` | Absolute imports, modern iterator ABC, lazy mapping views, `Collection`, `Reversible`, `ByteString` | `PSF.txt` and repository license |
| `Lib/queue.py` | Repository `lib-python/2.7/Queue.py` | New-style base class | `PSF.txt` and repository license |
| `Lib/ipaddress.py` | PyPI ipaddress 1.0.23 | None | `ipaddress-1.0.23-LICENSE.txt` |
| `Lib/enum.py` | PyPI enum34 1.1.10, `enum/__init__.py` | Single-module layout | `enum34-1.1.10-LICENSE` |
| `Lib/contextlib.py` | Repository `lib-python/2.7/contextlib.py` | Added `suppress` | `PSF.txt` and repository license |
| `Lib/__future__.py` | Repository `lib-python/2.7/__future__.py` | Added postponed annotations feature | `PSF.txt` and repository license |
| `Lib/importlib/__init__.py` | Repository `lib-python/2.7/importlib/__init__.py` | Package layout | `PSF.txt` and repository license |
| `Lib/importlib/metadata.py` | Local implementation | Filesystem discovery; no zip distributions or entry points | Repository license |

Port source wheels:

```text
ipaddress-1.0.23-py2.py3-none-any.whl
SHA256 6e0f4a39e66cb5bb9a137b00276a2eff74f93b71dcbdad6f10ff7df9d3557fcc
enum34-1.1.10-py3-none-any.whl
SHA256 c3858660960c984d6ab0ebad691265180da2b43f07e061c0f8dca9ef3cffd328
```

Release sources are available from `https://pypi.org/project/<name>/<version>/`.
`pathlib2` 2.1.0's wheel does not include its license file; the full original
`LICENSE.rst` was obtained from its corresponding source distribution:

```text
https://files.pythonhosted.org/packages/c9/27/8448b10d8440c08efeff0794adf7d0ed27adb98372c70c7b38f3947d4749/pathlib2-2.1.0.tar.gz
SHA256 deb3a960c1d55868dfbcac98432358b92ba89d95029cddd4040db1f27405055c
```

These are bounded ports, not the Python 3.15 standard library. In particular,
modern dataclasses options, pathlib platform behavior, typing internals and the
complete modern iteration/container APIs have not been migrated or certified.
