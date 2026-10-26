#!/usr/bin/env bash
# Undo the SITE part of a commit (everything except .github/), so the bot never needs the `workflows` permission (25 Oct 2026).
# Files the commit added are removed; changed/deleted ones are restored from its parent. Usage: scripts/revert_site.sh <sha>
set -euo pipefail
sha="$1"
git diff --name-status --no-renames "$sha^" "$sha" | while IFS=$'\t' read -r st f; do
  case "$f" in .github/*) continue;; esac
  if [ "$st" = "A" ]; then git rm -q --ignore-unmatch -- "$f"; else git checkout "$sha^" -- "$f"; fi
done
# A parent snapshot can still contain the dead MapTiler key (403 Invalid key) and list MapTiler first.
# Strip that key from every restored file so no revert can put it back. An empty MapTiler key is skipped,
# which leaves OpenStreetMap (no key required) as the default in the tiles.js those commits restore.
py=$(command -v python3 || command -v python)
"$py" - << 'PY'
import os, re, subprocess
files = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '-z'])
dead = 'xl3BtUpx' + 'Qak69583G9Q6'
field = re.compile(r"(name:\s*'maptiler'\s*,\s*key:\s*)'(?:\\'|[^'])*'")
urlkey = re.compile(r"(https://api\.maptiler\.com\S*?[?&]key=)(?!\{key\})([^&\s'\"<>]+)")
for name in files.decode('utf-8', 'surrogateescape').split('\0'):
    if not name or not os.path.isfile(name):
        continue
    raw = open(name, 'rb').read()
    if b'\0' in raw[:1024]:
        continue
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        continue
    new = field.sub(r"\1''", text.replace(dead, ''))
    new = urlkey.sub(r'\1', new)
    if new != text:
        open(name, 'w', encoding='utf-8').write(new)
        subprocess.check_call(['git', 'add', '--', name])
PY
if git diff --cached --quiet; then echo "nothing to revert outside .github/"; exit 0; fi
git commit -q -m "Auto-revert site files of ${sha:0:9} (live check failed; workflow files untouched)"
echo "reverted site files of $sha"
