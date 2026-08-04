# -*- coding: utf-8 -*-
"""Fetch http://127.0.0.1:5000/ and verify responsibility-area UI markers."""
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

URL = "http://127.0.0.1:5000/"
try:
    with urllib.request.urlopen(URL, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
except Exception as e:
    print("ERR:", e)
    sys.exit(1)

checks = [
    ("HAS_RESP_AREA", "พื้นที่รับผิดชอบ" in html),
    ("HAS_GRID", "resp-tambon-grid" in html),
    ("HAS_SETUP", "setup-section" in html),
    ("HAS_TAMBON_PANEL", "tambon-multi-panel" in html),
    ("HAS_CACHE_BUST", "area3" in html),
]

# Strip hidden blocks for visible-content checks
visible = re.sub(r"(?s)<div\s+hidden[^>]*>.*?</div>", "", html)
checks.append(("NO_VISIBLE_VILLAGE_OK", "เลือกหมู่บ้าน" not in visible))
old_geo = (
    "เลือกจังหวัด · อำเภอ · ตำบล · หมู่บ้าน" in visible
    or "เลือกจังหวัด·หมู่บ้าน" in visible.replace(" ", "")
)
checks.append(("NO_OLD_GEO_UI_OK", not old_geo))

for name, ok in checks:
    print(name if ok else "FAIL_" + name.replace("HAS_", "NO_").replace("NO_", "BAD_"))

# Save for inspection
out = sys.argv[1] if len(sys.argv) > 1 else "_served.html"
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("SAVED=" + out)
all_ok = all(ok for _, ok in checks)
sys.exit(0 if all_ok else 2)
