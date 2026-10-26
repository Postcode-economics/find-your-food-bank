"""Pending-list sections for Dean. Nothing here deletes a place.

publish_gate.py rebuilds reports/pending_dean.md and keeps each <!-- tag --> block.
Add a tag there when a new section is written, or the next publish wipes it.
"""
import os, re

def write_marked(path, tag, body):
    """Replace the marked section, or append it. The body is the lines between the markers."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    t = open(path, encoding='utf-8').read() if os.path.exists(path) else '# Pending for Dean\n'
    block = '<!-- %s -->\n%s\n<!-- /%s -->' % (tag, (body or '').rstrip('\n'), tag)
    pat = re.compile(r'(?s)\n*<!-- %s -->.*?<!-- /%s -->\n?' % (re.escape(tag), re.escape(tag)))
    if pat.search(t):
        t = pat.sub('\n\n' + block + '\n', t, count=1)
    else:
        t = t.rstrip() + '\n\n' + block + '\n'
    open(path, 'w', encoding='utf-8').write(t if t.endswith('\n') else t + '\n')

def hold_closed_shelters(fresh):
    """Own-site-closed shelters stay in fresh. Returns the pending rows. Does not delete any."""
    held = []
    for x in fresh:
        ev = x.pop('_own_site_closed', None)
        if not ev:
            continue
        held.append({
            'id': x.get('id') or '',
            'name': x.get('name') or x.get('id') or '',
            'evidence': ev,
            'website': x.get('website') or x.get('source_url') or '',
        })
    return held

def shelter_closure_body(held):
    lines = ['- %s (%s) — own site says closed; still on the map until you say to remove it. %s — %s'
             % (h['name'], h['id'], h['evidence'], h['website']) for h in held] or ['- none']
    return '\n'.join([
        '## Shelters the own site calls closed — waiting for your OK (%d)' % len(held),
        '',
        'Nothing in this list was removed. Say yes before one comes off the map.',
        '',
    ] + lines)

def feed_drop_ids(prev_ids, ids):
    """Ids that were on the map last run and are not in this feed. Not a removal."""
    if not prev_ids:
        return []
    return sorted(set(prev_ids) - set(ids))

def feed_drop_body(ids):
    lines = ['- %s — dropped out of the feed. On this list for you; not treated as removed.' % x for x in ids] or ['- none']
    return '\n'.join([
        '## Food banks that dropped out of the feed (%d)' % len(ids),
        '',
        'These left the feed this run. They are not recorded as removed. Confirm each one before it is treated as gone.',
        '',
    ] + lines)

def phone_hold_body(rows):
    """rows: {id, name, website, why}. The number is not included."""
    lines = ['- %s (%s) — %s — %s' % (h.get('name') or h.get('id'), h.get('id'), h.get('why'), h.get('website') or '')
             for h in rows] or ['- none']
    return '\n'.join([
        '## Phone numbers held (%d)' % len(rows),
        '',
        'The page says not to phone, or the number is a council switchboard the page does not name as the out-of-hours line. The number is not copied here.',
        '',
    ] + lines)
