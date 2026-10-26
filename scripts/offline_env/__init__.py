"""Offline test harness (rule 25). Import from tests; do not hit helpmap.uk or map tiles.

    from offline_env import launch, offline_context, start
"""
from .harness import (
    BLANK_PNG,
    HELP_MAP_ORIGIN,
    SNAPSHOT_FILES,
    TILE_HOSTS,
    ExternalRequest,
    Offline,
    RequestLog,
    Routed,
    assert_log_clean,
    classify,
    is_helpmap,
    is_loopback,
    is_tile_host,
    launch,
    offline_context,
    serve,
    snapshot,
    start,
)

try:
    import pytest
except ImportError:  # pytest is only needed when a test opts into the fixture
    pytest = None

if pytest is not None:
    @pytest.fixture
    def offline():
        """Serve the frozen snapshot and fail the test if any external host was requested.

        Register this plugin with ``pytest_plugins = ['offline_env']`` (and put ``scripts``
        on ``PYTHONPATH``, which ``scripts/offline_env/run.sh`` already does).
        """
        env = start()
        try:
            yield env
        finally:
            try:
                env.assert_clean()
            finally:
                env.close()

__all__ = [
    'BLANK_PNG',
    'HELP_MAP_ORIGIN',
    'SNAPSHOT_FILES',
    'TILE_HOSTS',
    'ExternalRequest',
    'Offline',
    'RequestLog',
    'Routed',
    'assert_log_clean',
    'classify',
    'is_helpmap',
    'is_loopback',
    'is_tile_host',
    'launch',
    'offline_context',
    'serve',
    'snapshot',
    'start',
]
if pytest is not None:
    __all__.append('offline')
