"""Optional CI sharding (PYTEST_SHARD=i/N): sorted test ids are split round-robin so every test runs in exactly one shard.
Unset = full run. Selected ids go to $PYTEST_SHARD_LIST so CI can check the shard union equals the full collection."""
import os

def pytest_collection_modifyitems(config, items):
    shard = os.environ.get('PYTEST_SHARD')
    if not shard: return
    i, k = (int(x) for x in shard.split('/')); assert 1 <= i <= k, shard
    ids = sorted(it.nodeid for it in items); keep = set(ids[j] for j in range(len(ids)) if j % k == i - 1)
    dropped = [it for it in items if it.nodeid not in keep]; items[:] = [it for it in items if it.nodeid in keep]
    config.hook.pytest_deselected(items=dropped)
    out = os.environ.get('PYTEST_SHARD_LIST')
    if out: open(out, 'w').write(''.join(x + '\n' for x in sorted(keep)))
