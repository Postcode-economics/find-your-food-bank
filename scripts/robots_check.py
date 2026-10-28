"""Decide whether robots.txt asks us not to fetch a path. Opening hours are never guessed from a blocked page."""

def blocked(text, path):
    """True when the User-agent: * group disallows `path`. Empty or missing text: not blocked.
    An empty Disallow means nothing is disallowed. This does not invent hours."""
    if not text: return False
    path = path if str(path).startswith("/") else "/" + str(path or "")
    groups, agents, rules, seen = [], [], [], False
    def flush():
        nonlocal agents, rules, seen
        if agents: groups.append((agents, rules))
        agents, rules, seen = [], [], False
    for raw in str(text).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line: continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            if seen: flush()
            agents.append(val)
        elif key == "disallow" and agents:
            seen = True; rules.append(val)
    flush()
    star = next((r for a, r in groups if "*" in a), None)
    if not star: return False
    return any(rule and (rule == "/" or path.startswith(rule)) for rule in star)
