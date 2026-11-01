#!/usr/bin/env python3
"""Reset man-google-* manual rows and re-apply from logs/google_a_items.json."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAN = ROOT / "overrides" / "shelters_manual.json"
VER = ROOT / "overrides" / "shelters_verified.json"
AP = ROOT / "overrides" / "approved_new_places.json"
PH = ROOT / "overrides" / "phone_baseline.json"


def main():
    manual = json.load(open(MAN, encoding="utf-8"))
    manual = [x for x in manual if not x.get("id", "").startswith("man-google-")]
    MAN.write_text(json.dumps(manual, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ver = json.load(open(VER, encoding="utf-8"))
    for k in list(ver.keys()):
        if k.startswith("man-google-"):
            del ver[k]
    VER.write_text(json.dumps(ver, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ap = json.load(open(AP, encoding="utf-8"))
    ap["shelters"] = {k: v for k, v in ap["shelters"].items() if not k.startswith("man-google-")}
    AP.write_text(json.dumps(ap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ph = json.load(open(PH, encoding="utf-8"))
    for k in list(ph.keys()):
        if k.startswith("man-google-"):
            del ph[k]
    PH.write_text(json.dumps(ph, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    subprocess.check_call(["python3", "scripts/apply_google_a_items.py"], cwd=ROOT)


if __name__ == "__main__":
    main()
