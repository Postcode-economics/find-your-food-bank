# With HELPMAP_SHARD="i/N" set (tests.yml browser and WebKit jobs), run only this job's share of the collected
# tests, whole modules at a time, and write logs/shards/<HELPMAP_SHARD_SUITE>-<i>.json for the coverage check.
# Unset (the plain test job, local runs) nothing changes.
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import shard  # noqa: E402

_STATE = {}


def _weights():
    try:
        w = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shard_weights.json'), encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return w.get(os.environ.get('HELPMAP_SHARD_SUITE', ''), w.get('modules', {}))


def pytest_collection_modifyitems(config, items):
    if not shard.spec():
        return
    module = lambda it: it.nodeid.split('::', 1)[0]
    mine = set(id(it) for it in shard.pick(items, group=module, weights=_weights()))
    keep = [it for it in items if id(it) in mine]
    drop = [it for it in items if id(it) not in mine]
    _STATE.update(expected=[it.nodeid for it in items], picked=[it.nodeid for it in keep], ran=[])
    if drop:
        config.hook.pytest_deselected(items=drop)
    items[:] = keep


def pytest_runtest_logreport(report):
    # A test counts as run once it reports its call, or a skip/error from setup (same outcome as an unsharded run).
    if 'ran' in _STATE and (report.when == 'call' or report.outcome != 'passed'):
        _STATE['ran'].append(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    if 'ran' in _STATE:
        ran = list(dict.fromkeys(_STATE['ran']))
        p = shard.write_report(os.environ.get('HELPMAP_SHARD_SUITE', 'pytest'), _STATE['expected'], _STATE['picked'], ran)
        print('\nshard %s: %d of %d tests picked, %d ran (%s)' % (os.environ['HELPMAP_SHARD'], len(_STATE['picked']),
                                                                 len(_STATE['expected']), len(ran), p))
