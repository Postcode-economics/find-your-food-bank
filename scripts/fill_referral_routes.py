"""Sweep step: repair referral cards in shelters.js whose referral_route was dropped (copy of their own checked line)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_js, write_js, fill_referral_routes
d = load_js("shelters.js", "SHELTERS")
fixed = fill_referral_routes(d.get("items", []))
if fixed: write_js("shelters.js", "SHELTERS", d)
print("referral_route filled:", fixed)
