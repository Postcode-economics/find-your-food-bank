"""Pick the pytest files a change can affect (Dean 2 Nov 2026: targeted tests on PRs).

Usage: python scripts/select_tests.py FILE...   (changed files, repo-relative)
Prints either "ALL" or the test files to run, one per line. Rules:
  * a changed tests/test_*.py runs itself;
  * any other file maps to every test that names it (module name for scripts/*.py, file
    name otherwise), following scripts that import a changed script, transitively;
  * shared test helpers, fixtures, CI config, requirements, or ANY file no test names -> ALL.
Main, the nightly run and manual runs always run ALL (see tests.yml).
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALWAYS_ALL = re.compile(r'^(\.github/|requirements[^/]*\.txt$|pytest\.ini$|pyproject\.toml$|setup\.cfg$|conftest\.py$|tests/(?!test_)[^/]+$|tests/conftest\.py$)')

def read(p):
    try:
        return open(p, encoding='utf-8', errors='replace').read()
    except OSError:
        return ''

def main(files):
    tests = sorted('tests/' + f for f in os.listdir(os.path.join(ROOT, 'tests')) if f.startswith('test_') and f.endswith('.py'))
    tsrc = {t: read(os.path.join(ROOT, t)) for t in tests}
    scripts = {f[:-3]: read(os.path.join(ROOT, 'scripts', f)) for f in os.listdir(os.path.join(ROOT, 'scripts')) if f.endswith('.py')}
    if not files or len(files) >= 300:
        return None, 'no diff or very large diff'
    pick = set()
    for f in files:
        if ALWAYS_ALL.search(f):
            return None, '%s is shared test/CI config' % f
        if re.match(r'^tests/test_[^/]+\.py$', f):
            if os.path.exists(os.path.join(ROOT, f)):
                pick.add(f)
            continue
        if f.startswith('tests/fixtures/'):
            names = [os.path.basename(f), f[len('tests/'):]]
        elif re.match(r'^scripts/[^/]+\.py$', f):
            stem = os.path.basename(f)[:-3]
            mods, todo = {stem}, [stem]
            while todo:  # scripts that import a changed script are affected too
                m = todo.pop()
                for s, src in scripts.items():
                    if s not in mods and re.search(r'^\s*(from\s+%s\s+import|import\s+[\w, ]*\b%s\b)' % (m, m), src, re.M):
                        mods.add(s); todo.append(s)
            names = sorted(mods)
        else:
            names = [f, os.path.basename(f)]
        hit = set()
        for t, src in tsrc.items():
            for n in names:
                pat = r'\b%s\b' % re.escape(n) if n.isidentifier() else re.escape(n)
                if re.search(pat, src):
                    hit.add(t); break
        if not hit:
            return None, '%s is not mapped to any test' % f
        pick |= hit
    return sorted(pick), '%d changed file(s) -> %d of %d test files' % (len(files), len(pick), len(tests))

if __name__ == '__main__':
    sel, why = main([a.strip() for a in sys.argv[1:] if a.strip()])
    print(why, file=sys.stderr)
    print('ALL' if sel is None else '\n'.join(sel))
