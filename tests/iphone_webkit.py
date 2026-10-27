"""The default iPhone WebKit browser context.

A real iPhone allows the service worker. Playwright with the worker blocked is not
that phone: the in-page fetch of an OpenFreeMap style or tilejson comes back 200 image/png,
MapLibre throws 'The string did not match the expected pattern', and the map stays grey.
That grey map was a test artefact. Callers that genuinely need the worker off use a test
named *_sw_off and pass service_workers='block' themselves; this helper does not.
"""
DEVICES = ('iPhone 13', 'iPhone SE')


def iphone_context(playwright, browser, device='iPhone 13', proxy=None, service_workers='allow', **extra):
    """iPhone 13 or iPhone SE, WebKit, service worker allowed unless the caller overrides it."""
    kw = dict(playwright.devices[device])
    kw.pop('default_browser_type', None)
    kw['ignore_https_errors'] = True
    if proxy is not None:
        kw['proxy'] = {'server': proxy.url}
    kw.update(extra)
    # Default is allow. A caller that passes service_workers='block' is a *_sw_off case.
    kw['service_workers'] = extra.get('service_workers', service_workers)
    return browser.new_context(**kw)
