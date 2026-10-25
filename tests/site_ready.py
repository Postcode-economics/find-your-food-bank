"""Open the local map for a browser check.

`wait_until="networkidle"` also waits for map tiles. A tile connection that
stays open makes `Page.goto` time out after the local files have already
loaded. These checks need the search box, the food-bank data and the map pane, not the tiles.
"""
READY = "() => !!(document.getElementById('q') && window.FB_DATA && FB_DATA.items && FB_DATA.items.length > 100 && document.querySelector('#map .leaflet-pane'))"

def open_map(page, url):
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function(READY)

def reload_map(page):
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(READY)
