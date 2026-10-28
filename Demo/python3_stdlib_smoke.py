# -*- coding: utf-8 -*-
"""Run Python 3 standard-library snippets against CPython or this Jython build.

From the repository root:
    python3 -B Demo/python3_stdlib_smoke.py
    java -Dpython.home=dist -cp 'dist/jython-dev.jar:extlibs/*' \
        org.python.util.jython -B Demo/python3_stdlib_smoke.py

Pass snippet names to run only those cases, for example: json datetime.
Use --list to list names, or --show [names...] to print standalone snippets.
Exit status: 0 = all selected cases pass, 1 = incompatibility, 2 = usage error.

No third-party packages, network access, or persistent data files are needed.
Snippets intentionally use Python 3 imports without Python 2 fallback aliases.
Sources are compiled separately so one unsupported syntax/import cannot prevent
other cases from running. Passing a case does not imply full module support.
"""
from __future__ import print_function

import sys


SNIPPETS = [
    ("json", "JSON serialization", '''\
import json

payload = {"name": "Jython", "values": [1, 2, 3], "active": True}
encoded = json.dumps(payload, sort_keys=True)
assert json.loads(encoded) == payload
print(f"JSON: {encoded}")
'''),
    ("re", "Regular expressions", r'''
import re

text = "order-123, order-456"
numbers = re.findall(r"order-(\d+)", text)
assert numbers == ["123", "456"]
assert re.sub(r"\d+", "N", text) == "order-N, order-N"
print(f"Matches: {numbers}")
'''),
    ("numbers", "math / decimal / fractions", '''\
import math
from decimal import Decimal
from fractions import Fraction

assert math.sqrt(81) == 9.0
assert math.factorial(5) == 120
assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
assert Fraction(1, 3) + Fraction(1, 6) == Fraction(1, 2)
print(f"sqrt(81): {math.sqrt(81):.1f}")
'''),
    ("collections", "collections / itertools", '''\
from collections import Counter, defaultdict, deque
from itertools import chain

counts = Counter(["red", "blue", "red"])
assert counts["red"] == 2
queue = deque([1, 2])
queue.append(3)
assert queue.popleft() == 1
groups = defaultdict(list)
groups["odd"].append(3)
assert groups["odd"] == [3]
assert list(chain([1, 2], [3])) == [1, 2, 3]
print(f"Red count: {counts['red']}")
'''),
    ("datetime", "datetime / time", '''\
from datetime import datetime, timedelta
import time

start = datetime.strptime("2026-10-28 12:30:00", "%Y-%m-%d %H:%M:%S")
end = start + timedelta(days=3)
assert end.strftime("%Y-%m-%d") == "2026-10-31"
assert (end - start).total_seconds() == 259200.0
assert time.gmtime(0).tm_year == 1970
print(f"Three days later: {end:%Y-%m-%d %H:%M:%S}")
'''),
    ("os_sys", "os / sys", '''\
import os
import sys

path = os.path.join("example", "report.txt")
assert os.path.basename(path) == "report.txt"
assert os.path.splitext(path)[1] == ".txt"
assert os.path.isdir(os.getcwd())
assert sys.version_info[0] >= 2
print(f"Path: {path}; platform: {sys.platform}")
'''),
    ("csv_io", "csv / io in-memory round trip", '''\
import csv
import io

buffer = io.StringIO()
rows = [["name", "count"], ["apple", "3"], ["a,b", "4"]]
writer = csv.writer(buffer)
writer.writerows(rows)
buffer.seek(0)
assert list(csv.reader(buffer)) == rows
buffer.close()
print("CSV round trip: OK")
'''),
    ("binary", "hashlib / base64 / zlib", '''\
import base64
import hashlib
import zlib

data = b"hello"
assert base64.b64encode(data) == b"aGVsbG8="
assert base64.b64decode(base64.b64encode(data)) == data
assert zlib.decompress(zlib.compress(data)) == data
assert hashlib.sha256(data).digest() == base64.b64decode(
    b"LPJNul+wow4m6DsqxbninhsWHlwfp0JecwQzYpOLmCQ="
)
print(f"Compressed round trip: {len(data)} bytes")
'''),
    ("pathlib", "Python 3 pathlib", '''\
from pathlib import PurePosixPath

path = PurePosixPath("reports") / "summary.txt"
assert path.name == "summary.txt"
assert path.suffix == ".txt"
assert str(path.parent) == "reports"
print(f"Path: {path}")
'''),
    ("statistics", "Python 3 statistics", '''\
import statistics

values = [1, 2, 3, 4, 5]
assert statistics.mean(values) == 3
assert statistics.median(values) == 3
print(f"Mean: {statistics.mean(values)}")
'''),
    ("urllib_parse", "Python 3 urllib.parse module name", '''\
from urllib.parse import parse_qs, urlencode, urlparse

query = urlencode({"q": "hello world"})
assert parse_qs(query) == {"q": ["hello world"]}
assert urlparse("https://example.com/search?" + query).hostname == "example.com"
print(f"Query: {query}")
'''),
    ("queue", "Python 3 queue module name", '''\
from queue import Queue

queue = Queue()
queue.put("job")
assert queue.get_nowait() == "job"
queue.task_done()
assert queue.empty()
print("Queue: OK")
'''),
    ("asyncio", "Python 3 asyncio without async/await syntax", '''\
import asyncio

loop = asyncio.new_event_loop()
try:
    result = loop.run_until_complete(asyncio.sleep(0, result=42))
    assert result == 42
    print(f"Async result: {result}")
finally:
    loop.close()
'''),
    ("sqlite3", "SQLite in-memory database", '''\
import sqlite3

connection = sqlite3.connect(":memory:")
try:
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE items (name TEXT)")
    cursor.execute("INSERT INTO items VALUES (?)", ("apple",))
    cursor.execute("SELECT name FROM items")
    assert cursor.fetchone() == ("apple",)
    print("SQLite: OK")
finally:
    connection.close()
'''),
    ("timezone", "Python 3 datetime.timezone API", '''\
from datetime import datetime, timedelta, timezone

moment = datetime(2026, 10, 28, 12, 30, tzinfo=timezone.utc)
assert moment.utcoffset() == timedelta(0)
assert moment.isoformat() == "2026-10-28T12:30:00+00:00"
print(f"UTC: {moment.isoformat()}")
'''),
    ("lru_cache", "Python 3 functools.lru_cache API", '''\
from functools import lru_cache

@lru_cache(maxsize=16)
def square(value):
    return value * value

assert square(4) == 16
assert square(4) == 16
assert square.cache_info().hits == 1
print(f"Cache hits: {square.cache_info().hits}")
'''),
]


def main(arguments):
    show = bool(arguments and arguments[0] == "--show")
    if arguments == ["--list"]:
        for name, description, source in SNIPPETS:
            print("{0}: {1}".format(name, description))
        return 0
    if show:
        arguments = arguments[1:]
    names = [name for name, description, source in SNIPPETS]
    unknown = [name for name in arguments if name not in names]
    if unknown:
        print("Unknown cases: {0}. Use --list for valid names.".format(
            ", ".join(unknown)))
        return 2
    selected = [case for case in SNIPPETS if not arguments or case[0] in arguments]
    if show:
        for name, description, source in selected:
            print("# {0}: {1}".format(name, description))
            print(source)
        return 0

    print("Runtime: {0}".format(sys.version.replace("\n", " ")))
    failures = []
    for name, description, source in selected:
        print("\n[{0}] {1}".format(name, description))
        try:
            code = compile(source, "<stdlib:{0}>".format(name), "exec")
        except SyntaxError as error:
            status = "SYNTAX_FAIL"
            detail = "{0}: {1}".format(type(error).__name__, error)
        else:
            namespace = {"__name__": "__main__"}
            try:
                exec(code, namespace)
            except ImportError as error:
                status = "IMPORT_FAIL"
                detail = "{0}: {1}".format(type(error).__name__, error)
            except Exception as error:
                status = "RUNTIME_FAIL"
                detail = "{0}: {1}".format(type(error).__name__, error)
            else:
                print("PASS")
                continue
        failures.append((name, status, detail))
        print("{0}: {1}".format(status, detail))

    print("\nSummary: {0} passed, {1} failed, {2} total".format(
        len(selected) - len(failures), len(failures), len(selected)))
    for name, status, detail in failures:
        print("  {0}: {1}: {2}".format(name, status, detail))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
