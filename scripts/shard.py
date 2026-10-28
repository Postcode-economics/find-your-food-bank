"""Split one CI check across parallel jobs without dropping a single case (Dean 28 Oct 2026: faster test runs).

HELPMAP_SHARD="i/N" (1-based) picks this job's share; unset means everything (local runs, deploy-check.yml).
Cases are grouped (a pytest module stays whole, so its order and class fixtures are unchanged) and groups are
dealt out longest-first by weight, so every shard computes the same split from the same case list.
Each shard writes logs/shards/<suite>-<i>.json: the full case list it saw, the cases dealt to it and the cases
that actually reported. `python scripts/shard.py verify <suite> <N> <dir>` exits 1 unless all N reports are there,
agree on the full list, and between them ran every case exactly once."""
import glob, json, os, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DEFAULT_WEIGHT = 5.0


def spec(env=None):
    v = (os.environ if env is None else env).get('HELPMAP_SHARD', '').strip()
    if not v:
        return None
    i, n = (int(x) for x in v.split('/'))
    if n < 1 or not 1 <= i <= n:
        raise ValueError('HELPMAP_SHARD=%r: want i/N with 1 <= i <= N' % v)
    return i, n


def assign(groups, n, weights=None):
    """group -> shard 1..n. Heaviest group first onto the lightest shard; ties broken by name, so it is deterministic."""
    w = weights or {}
    load = [0.0] * n
    out = {}
    for g in sorted(set(groups), key=lambda g: (-w.get(g, DEFAULT_WEIGHT), g)):
        s = min(range(n), key=lambda j: (load[j], j))
        out[g] = s + 1
        load[s] += w.get(g, DEFAULT_WEIGHT)
    return out


def pick(cases, group=lambda c: c, weights=None, env=None):
    """This shard's cases, in their original order (all of them when HELPMAP_SHARD is unset)."""
    cases = list(cases)
    sp = spec(env)
    if not sp:
        return cases
    i, n = sp
    a = assign([group(c) for c in cases], n, weights)
    return [c for c in cases if a[group(c)] == i]


def write_report(suite, expected, picked, ran, env=None):
    sp = spec(env)
    if not sp:
        return None
    i, n = sp
    d = os.path.join(ROOT, 'logs', 'shards')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, '%s-%d.json' % (suite, i))
    json.dump(dict(suite=suite, shard=i, of=n, expected=list(expected), picked=list(picked), ran=list(ran)),
              open(p, 'w', encoding='utf-8'), indent=1)
    return p


def verify(suite, n, d):
    """Problems found in the N shard reports under d (empty list = every case ran exactly once)."""
    probs, reps = [], {}
    for p in glob.glob(os.path.join(d, '**', '%s-*.json' % suite), recursive=True):
        r = json.load(open(p, encoding='utf-8'))
        if r.get('suite') != suite:
            continue
        if r['shard'] in reps:
            probs.append('shard %d reported twice' % r['shard'])
        reps[r['shard']] = r
    missing = [i for i in range(1, n + 1) if i not in reps]
    if missing:
        probs.append('no report from shard(s) %s' % missing)
    for i, r in sorted(reps.items()):
        if r['of'] != n:
            probs.append('shard %d was run as 1 of %d, expected %d' % (i, r['of'], n))
    if not reps:
        return probs
    full = sorted(next(iter(reps.values()))['expected'])
    for i, r in sorted(reps.items()):
        if sorted(r['expected']) != full:
            probs.append('shard %d saw a different case list (%d cases, others %d)' % (i, len(r['expected']), len(full)))
        not_run = sorted(set(r['picked']) - set(r['ran']))
        if not_run:
            probs.append('shard %d did not run %d of its cases: %s' % (i, len(not_run), not_run[:10]))
    seen = {}
    for i, r in sorted(reps.items()):
        for c in r['ran']:
            seen.setdefault(c, []).append(i)
    twice = sorted(c for c, s in seen.items() if len(s) > 1)
    if twice:
        probs.append('%d case(s) ran in more than one shard: %s' % (len(twice), twice[:10]))
    lost = sorted(set(full) - set(seen))
    if lost:
        probs.append('%d case(s) ran in no shard: %s' % (len(lost), lost[:10]))
    extra = sorted(set(seen) - set(full))
    if extra:
        probs.append('%d case(s) ran that are not in the case list: %s' % (len(extra), extra[:10]))
    return probs


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[1] != 'verify':
        sys.exit('usage: python scripts/shard.py verify <suite> <N> <dir>')
    suite, n, d = sys.argv[2], int(sys.argv[3]), sys.argv[4]
    probs = verify(suite, n, d)
    for p in probs:
        print('::error::%s: %s' % (suite, p))
    if not probs:
        tot = sum(len(json.load(open(p))['ran']) for p in glob.glob(os.path.join(d, '**', '%s-*.json' % suite), recursive=True))
        print('%s: all %d shards reported; %d cases, each ran exactly once' % (suite, n, tot))
    sys.exit(1 if probs else 0)
