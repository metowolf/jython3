"""Run non-interactive existing Java tests without Ant's optional JUnit task.

Build first with ant jar copy-dev compile-test. Run this file with Python 3.9+.
The candidate/exclusion rules follow javatest-built in build.xml. Each concrete
class executes in its own JVM; failures do not hide results from later classes.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=ROOT / 'build/cpython-validation/junit-direct')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    reports = args.reports.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    classes = reports / 'runner'
    classes.mkdir(exist_ok=True)
    if not shutil.which('java') or not shutil.which('javac'):
        parser.error('JDK java and javac are required')
    classpath = os.pathsep.join(map(str, (ROOT / 'build/exposed', ROOT / 'build/classes',
                                        ROOT / 'build/testclasses', ROOT / 'extlibs/*')))
    subprocess.run(['javac', '-cp', classpath, '-d', str(classes),
                    str(ROOT / 'tests/cpython/java/JUnitDiscovery.java')], check=True, timeout=60)
    source = ROOT / 'tests/java'
    candidates, excluded = [], []
    for path in sorted(source.rglob('*Test*.java')):
        relative = path.relative_to(source)
        if (path.name == 'InterpTestCase.java' or path.name.startswith('jythonTest')
                or relative.as_posix().startswith('org/python/antlr/')):
            excluded.append(relative.as_posix())
        else:
            candidates.append('.'.join(relative.with_suffix('').parts))
    discovery = subprocess.run(['java', '-cp', str(classes) + os.pathsep + classpath,
                                'JUnitDiscovery', *candidates], capture_output=True,
                               text=True, check=True, timeout=60)
    (reports / 'discovery.log').write_text(discovery.stdout + discovery.stderr)
    tests = [line[5:] for line in discovery.stdout.splitlines() if line.startswith('TEST ')]
    helpers = [line[7:] for line in discovery.stdout.splitlines() if line.startswith('HELPER ')]
    summary = {'excluded_sources': excluded, 'helper_classes': helpers, 'results': []}
    for name in tests:
        cp = classpath
        if name.startswith('org.python.tests.imp.'):
            cp += os.pathsep + str(ROOT / 'tests/python')
        command = ['java', '-Xmx768m', '-Dpython.home=' + str(ROOT / 'dist'),
                   '-Dpython.test.source.dir=' + str(source), '-cp', cp,
                   'org.junit.runner.JUnitCore', name]
        try:
            result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, errors='replace', timeout=args.timeout)
            output = result.stdout + result.stderr
            passed = re.search(r'OK \((\d+) tests?\)', output)
            failed = re.search(r'Tests run: (\d+),\s+Failures: (\d+)', output)
            count = int(passed[1]) if passed else int(failed[1]) if failed else 0
            status = 'failed' if result.returncode != 0 else 'passed' if count else 'no_cases'
            entry = {'class': name, 'status': status, 'exit_code': result.returncode, 'run': count,
                     'failures': int(failed[2]) if failed else 0}
        except subprocess.TimeoutExpired as error:
            output = str(error) + '\n' + (error.stdout or b'').decode('utf-8', 'replace')
            entry = {'class': name, 'status': 'timeout', 'run': 0, 'failures': 0}
        (reports / (name + '.log')).write_text(output)
        summary['results'].append(entry)
        (reports / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(name + ': ' + entry['status'] + ' (' + str(entry['run']) + ')', flush=True)
    failed = sum(item['status'] in ('failed', 'timeout') for item in summary['results'])
    print('Classes: %d; failed/timed out: %d; cases reported: %d' % (
        len(tests), failed, sum(item['run'] for item in summary['results'])))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
