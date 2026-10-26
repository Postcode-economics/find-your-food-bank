"""Browser checks answer tile hosts locally. A context created in a test gets the same stub."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import offline_env


def pytest_configure(config):
    os.environ.setdefault('HELPMAP_OFFLINE', '1')
    try:
        from playwright.sync_api import Browser
    except Exception:
        return
    if getattr(Browser.new_context, '_helpmap_offline', False):
        return
    orig = Browser.new_context

    def new_context(self, **kw):
        c = orig(self, **kw)
        offline_env.stub(c)
        return c

    new_context._helpmap_offline = True
    Browser.new_context = new_context
    orig_page = Browser.new_page

    def new_page(self, **kw):
        pg = orig_page(self, **kw)
        offline_env.stub(pg.context)
        return pg

    Browser.new_page = new_page
