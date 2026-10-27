"""Say whether installed libraries match requirements.txt. Never installs or upgrades anything."""
import ast, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
REQ = os.path.join(ROOT, "requirements.txt")

def parse_pins(text):
    pins = {}
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"): continue
        if "==" not in line: continue
        name, ver = line.split("==", 1)
        pins[name.strip()] = ver.strip()
    return pins

def _key(name): return name.lower().replace("_", "-")

def third_party(scripts_dir):
    """Import names in scripts/ that are neither the standard library nor another script in that folder."""
    local = set()
    try: local = {os.path.splitext(f)[0] for f in os.listdir(scripts_dir) if f.endswith(".py")}
    except Exception: return []
    found = set()
    for f in sorted(local):
        try: tree = ast.parse(open(os.path.join(scripts_dir, f + ".py"), encoding="utf-8").read())
        except Exception: continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names: found.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    std = getattr(sys, "stdlib_module_names", set())
    return sorted(n for n in found if n not in local and n not in std and n != "__future__")

def report(requirements_text, scripts_dir, version_of):
    """Plain lines. version_of(name) is the installed version, or None. Nothing is upgraded."""
    pins = parse_pins(requirements_text)
    lines = []
    by_key = {_key(n): n for n in pins}
    for name in sorted(pins, key=str.lower):
        got = version_of(name)
        if got is None: lines.append("%s is pinned to %s and is not installed here" % (name, pins[name]))
        elif got != pins[name]: lines.append("%s is pinned to %s but this machine has %s" % (name, pins[name], got))
        else: lines.append("%s matches its pin %s" % (name, pins[name]))
    extra = [n for n in third_party(scripts_dir) if _key(n) not in by_key]
    lines.append("imported and not pinned: " + ", ".join(extra) if extra else "every third-party import is pinned")
    return lines

def installed(name):
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None

def note():
    try: text = open(REQ, encoding="utf-8").read()
    except Exception: return "requirements.txt could not be read - no effect"
    return " ".join(report(text, os.path.join(ROOT, "scripts"), installed))
