"""Strip non-visible HTML before classifying council pages (SWEP, emergency rest centres)."""
import re

_COMMENT = re.compile(r"(?s)<!--.*?-->")
_BLOCK = re.compile(r"(?is)<(script|style|svg|template|noscript).*?</\1>")
_TAG = re.compile(r"<[^>]+>")
_HIDDEN = re.compile(
    r'(?is)<([a-z0-9:-]+)\b[^>]*\b(?:hidden|aria-hidden\s*=\s*["\']true["\'])[^>]*>.*?</\1>'
)
_DISPLAY_NONE = re.compile(
    r'(?is)<([a-z0-9:-]+)\b[^>]*style\s*=\s*["\'][^"\']*display\s*:\s*none[^"\']*["\'][^>]*>.*?</\1>'
)


def html_to_visible_text(html):
    """Return plain text from visible page content only (no comments, hidden blocks, or scripts)."""
    h = html or ""
    h = _COMMENT.sub(" ", h)
    h = _BLOCK.sub(" ", h)
    h = _DISPLAY_NONE.sub(" ", h)
    h = _HIDDEN.sub(" ", h)
    h = _TAG.sub(" ", h)
    return re.sub(r"\s+", " ", h).strip()
