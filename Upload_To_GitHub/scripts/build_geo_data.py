#!/usr/bin/env python3
"""
Build bundled Thai geography JSON for T&V Automation.

Primary source (DOPA-style codes, includes villages):
  https://github.com/open-admin-data/thailand-administrative-divisions
  - data/all-province.json
  - data/all-district.json
  - data/all-subdistrict.json
  - data/villages-by-province/*.json

Outputs:
  data/provinces.json
  data/amphoes.json          # keyed by province_code
  data/tambons.json          # keyed by amphoe_code
  data/villages/{tambon_code}.json
  data/villages_index.json
  data/meta.json

Usage:
  python scripts/build_geo_data.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
VILLAGES_DIR = os.path.join(DATA_DIR, "villages")

RAW = "https://raw.githubusercontent.com/open-admin-data/thailand-administrative-divisions/main/data"
PROVINCE_URL = f"{RAW}/all-province.json"
DISTRICT_URL = f"{RAW}/all-district.json"
SUBDISTRICT_URL = f"{RAW}/all-subdistrict.json"
VILLAGES_API = (
    "https://api.github.com/repos/open-admin-data/"
    "thailand-administrative-divisions/contents/data/villages-by-province?ref=main"
)

USER_AGENT = "tv-automation-geo-builder/1.0"
SOURCE_URL = "https://github.com/open-admin-data/thailand-administrative-divisions"


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def local_name(obj: dict) -> str:
    name = obj.get("name") or {}
    if isinstance(name, dict):
        return (name.get("th") or name.get("local") or "").strip()
    return str(name or "").strip()


def parent_id(obj: dict) -> str:
    parent = obj.get("parent")
    if isinstance(parent, dict):
        return str(parent.get("id") or "").strip()
    if parent:
        return str(parent).strip()
    return ""


def build_admin_layers():
    print("Downloading provinces...")
    provinces_raw = fetch_json(PROVINCE_URL)
    print("Downloading districts (amphoes)...")
    districts_raw = fetch_json(DISTRICT_URL)
    print("Downloading subdistricts (tambons)...")
    tambons_raw = fetch_json(SUBDISTRICT_URL)

    provinces = []
    for p in provinces_raw:
        code = str(p.get("id") or "").strip()
        if not code:
            continue
        provinces.append(
            {
                "code": code,
                "name_th": local_name(p),
                "name_en": (p.get("name") or {}).get("en", "") if isinstance(p.get("name"), dict) else "",
            }
        )
    provinces.sort(key=lambda x: x["name_th"])

    amphoes = defaultdict(list)
    for d in districts_raw:
        code = str(d.get("id") or "").strip()
        pcode = parent_id(d)
        if not code or not pcode:
            continue
        amphoes[pcode].append(
            {
                "code": code,
                "name_th": local_name(d),
                "name_en": (d.get("name") or {}).get("en", "") if isinstance(d.get("name"), dict) else "",
                "province_code": pcode,
            }
        )
    for pcode in amphoes:
        amphoes[pcode].sort(key=lambda x: x["name_th"])

    tambons = defaultdict(list)
    for t in tambons_raw:
        code = str(t.get("id") or "").strip()
        acode = parent_id(t)
        if not code or not acode:
            continue
        zip_codes = t.get("zip_codes") or []
        zip_code = str(zip_codes[0]) if zip_codes else ""
        tambons[acode].append(
            {
                "code": code,
                "name_th": local_name(t),
                "name_en": (t.get("name") or {}).get("en", "") if isinstance(t.get("name"), dict) else "",
                "amphoe_code": acode,
                "zip_code": zip_code,
            }
        )
    for acode in tambons:
        tambons[acode].sort(key=lambda x: x["name_th"])

    write_json(os.path.join(DATA_DIR, "provinces.json"), provinces)
    write_json(os.path.join(DATA_DIR, "amphoes.json"), dict(amphoes))
    write_json(os.path.join(DATA_DIR, "tambons.json"), dict(tambons))

    meta = {
        "sources": {
            "admin": {
                "name": "open-admin-data/thailand-administrative-divisions",
                "url": SOURCE_URL,
                "license": "CC-BY-4.0",
                "files": [PROVINCE_URL, DISTRICT_URL, SUBDISTRICT_URL],
            }
        },
        "counts": {
            "provinces": len(provinces),
            "amphoes": sum(len(v) for v in amphoes.values()),
            "tambons": sum(len(v) for v in tambons.values()),
        },
    }
    print(
        f"Admin layers: {meta['counts']['provinces']} provinces, "
        f"{meta['counts']['amphoes']} amphoes, {meta['counts']['tambons']} tambons"
    )
    return meta


def village_moo(village_id: str, tambon_code: str) -> str:
    """DOPA village ids are typically tambon(6) + moo(2)."""
    vid = "".join(ch for ch in str(village_id) if ch.isdigit())
    tcode = "".join(ch for ch in str(tambon_code) if ch.isdigit())
    if tcode and vid.startswith(tcode) and len(vid) > len(tcode):
        return str(int(vid[len(tcode) :]))
    if len(vid) >= 2:
        return str(int(vid[-2:]))
    return ""


def build_villages(meta):
    print("Listing village province files...")
    listing = fetch_json(VILLAGES_API)
    files = [x for x in listing if x.get("type") == "file" and x.get("download_url")]
    print(f"Found {len(files)} province village files")

    by_tambon = defaultdict(list)
    total = 0

    for i, fmeta in enumerate(files, 1):
        url = fmeta["download_url"]
        fname = fmeta["name"]
        print(f"  [{i}/{len(files)}] {fname}")
        try:
            villages = fetch_json(url)
        except Exception as ex:
            print(f"    WARN: skip {fname}: {ex}")
            continue
        if not isinstance(villages, list):
            print(f"    WARN: unexpected shape in {fname}")
            continue
        for v in villages:
            if not isinstance(v, dict):
                continue
            tcode = parent_id(v)
            if not tcode:
                continue
            name = local_name(v)
            vid = str(v.get("id") or "")
            moo = village_moo(vid, tcode)
            if not name and not moo:
                continue
            by_tambon[tcode].append(
                {
                    "code": vid or f"{tcode}-{moo or total}",
                    "name_th": name or (f"หมู่ {moo}" if moo else "หมู่บ้าน"),
                    "moo": moo,
                }
            )
            total += 1

    os.makedirs(VILLAGES_DIR, exist_ok=True)
    for fn in os.listdir(VILLAGES_DIR):
        if fn.endswith(".json"):
            os.remove(os.path.join(VILLAGES_DIR, fn))

    for tcode, items in by_tambon.items():
        seen = set()
        unique = []
        for it in items:
            key = (it["name_th"], it["moo"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(it)
        unique.sort(
            key=lambda x: (
                int(x["moo"]) if str(x["moo"]).isdigit() else 999,
                x["name_th"],
            )
        )
        write_json(os.path.join(VILLAGES_DIR, f"{tcode}.json"), unique)

    index = {"tambon_codes": sorted(by_tambon.keys()), "total_villages": total}
    write_json(os.path.join(DATA_DIR, "villages_index.json"), index)

    meta["sources"]["villages"] = {
        "name": "open-admin-data/thailand-administrative-divisions",
        "url": SOURCE_URL,
        "path": "data/villages-by-province",
        "license": "CC-BY-4.0",
    }
    meta["counts"]["villages"] = total
    meta["counts"]["village_shards"] = len(by_tambon)
    print(f"Villages: {total} into {len(by_tambon)} tambon shards")
    return meta


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    meta = build_admin_layers()
    try:
        meta = build_villages(meta)
    except Exception as ex:
        print(f"WARN: village build failed ({ex}). API will fall back to หมู่ 1-20.")
        meta["counts"]["villages"] = 0
        meta["counts"]["village_shards"] = 0
        os.makedirs(VILLAGES_DIR, exist_ok=True)
    write_json(os.path.join(DATA_DIR, "meta.json"), meta)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
