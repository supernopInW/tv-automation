"""Load and serve bundled Thai geography data."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
VILLAGES_DIR = os.path.join(DATA_DIR, "villages")
CONFIG_DIR = os.path.join(BASE_DIR, "config")


def _read_json(path: str, default: Any = None):
    if not os.path.exists(path):
        return default if default is not None else {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_provinces():
    return _read_json(os.path.join(DATA_DIR, "provinces.json"), [])


@lru_cache(maxsize=1)
def load_amphoes_map():
    return _read_json(os.path.join(DATA_DIR, "amphoes.json"), {})


@lru_cache(maxsize=1)
def load_tambons_map():
    return _read_json(os.path.join(DATA_DIR, "tambons.json"), {})


@lru_cache(maxsize=1)
def load_presets():
    cfg = _read_json(os.path.join(CONFIG_DIR, "districts.json"), {"presets": []})
    return cfg.get("presets", [])


@lru_cache(maxsize=1)
def load_meta():
    return _read_json(os.path.join(DATA_DIR, "meta.json"), {})


def get_amphoes(province_code: str):
    return load_amphoes_map().get(str(province_code), [])


def get_tambons(amphoe_code: str):
    return load_tambons_map().get(str(amphoe_code), [])


@lru_cache(maxsize=1)
def load_all_villages():
    return _read_json(os.path.join(DATA_DIR, "villages_all.json"), {})


def get_villages(tambon_code: str):
    """Lazy-load village shard; fall back to synthetic หมู่ 1-20."""
    tcode = str(tambon_code or "").strip()
    if not tcode:
        return []
    all_v = load_all_villages()
    if tcode in all_v:
        return all_v[tcode]
    path = os.path.join(VILLAGES_DIR, f"{tcode}.json")
    if os.path.exists(path):
        villages = _read_json(path, [])
        if villages:
            return villages
    return [
        {"code": f"{tcode}-m{i}", "name_th": f"หมู่ {i}", "moo": str(i)}
        for i in range(1, 21)
    ]


def find_preset(preset_id: str = "sida"):
    for p in load_presets():
        if p.get("id") == preset_id:
            return p
    return None


def resolve_sida_codes():
    """Best-effort resolve อำเภอสีดา codes from loaded data if config is stale."""
    preset = find_preset("sida") or {}
    provinces = load_provinces()
    province = next((p for p in provinces if "นครราชสีมา" in p.get("name_th", "")), None)
    if not province:
        return preset
    amphoes = get_amphoes(province["code"])
    sida = next((a for a in amphoes if a.get("name_th") == "สีดา"), None)
    if not sida:
        return {
            **preset,
            "province_code": province["code"],
            "province_name": province["name_th"],
        }
    tambons = get_tambons(sida["code"])
    default_tambon = next(
        (t for t in tambons if "หนองตาดใหญ่" in t.get("name_th", "")),
        tambons[0] if tambons else None,
    )
    return {
        "id": "sida",
        "label": "อำเภอสีดา (นครราชสีมา)",
        "province_code": province["code"],
        "province_name": province["name_th"],
        "amphoe_code": sida["code"],
        "amphoe_name": sida["name_th"],
        "office_name": preset.get("office_name") or "สำนักงานเกษตรอำเภอสีดา",
        "default_tambon_code": default_tambon["code"] if default_tambon else "",
        "default_tambon_name": default_tambon["name_th"] if default_tambon else "หนองตาดใหญ่",
    }


def build_location_presets(office_name: str, tambon_name: str, villages: list | None = None):
    presets = []
    if office_name:
        presets.append({"value": office_name, "label": office_name})
        presets.append(
            {
                "value": f"สำนักงานเกษตรอำเภอ{office_name.replace('สนง.กษอ.', '')}",
                "label": f"สนง.เกษตรอำเภอ{office_name.replace('สนง.กษอ.', '')}",
            }
        )
    if tambon_name:
        tlabel = tambon_name if tambon_name.startswith("ตำบล") else f"ตำบล{tambon_name}"
        presets.append({"value": tlabel, "label": tlabel})
    for v in villages or []:
        name = v.get("name_th", "")
        moo = v.get("moo", "")
        if not name:
            continue
        label = name if not moo else f"{name} (ม.{moo})"
        value = name
        if moo and "หมู่" not in name:
            value = f"{name} หมู่ {moo}"
        if tambon_name and "ตำบล" not in value:
            tpart = tambon_name if tambon_name.startswith("ตำบล") else f"ตำบล{tambon_name}"
            value = f"{value} {tpart}"
        presets.append({"value": value, "label": label})
    presets.append({"value": "_custom", "label": "กำหนดเอง..."})
    # de-dupe
    seen = set()
    out = []
    for p in presets:
        if p["value"] in seen:
            continue
        seen.add(p["value"])
        out.append(p)
    return out


def default_location(
    office_name: str,
    tambon_name: str,
    village_name: str = "",
    moo: str = "",
    villages: list | None = None,
    moos: list | None = None,
):
    """Build PD_PLACE text. Supports one or many villages/moos."""
    village_names = [v for v in (villages or []) if v]
    if village_name and village_name not in village_names:
        village_names.insert(0, village_name)

    moo_list = [str(m).strip() for m in (moos or []) if str(m).strip()]
    if moo and str(moo).strip() and str(moo).strip() not in moo_list:
        moo_list.insert(0, str(moo).strip())
    # numeric sort when possible
    def _moo_key(x):
        return (0, int(x)) if str(x).isdigit() else (1, str(x))

    moo_list = sorted(dict.fromkeys(moo_list), key=_moo_key)
    tpart = ""
    if tambon_name:
        tpart = tambon_name if tambon_name.startswith("ตำบล") else f"ตำบล{tambon_name}"

    moo_text = ""
    if len(moo_list) == 1:
        moo_text = f"หมู่ {moo_list[0]}"
    elif len(moo_list) > 1:
        moo_text = f"หมู่ {', '.join(moo_list)}"

    if len(village_names) == 1:
        parts = [village_names[0]]
        if moo_text and "หมู่" not in village_names[0]:
            parts.append(moo_text)
        if tpart:
            parts.append(tpart)
        return " ".join(parts)
    if len(village_names) > 1:
        parts = [", ".join(village_names)]
        if moo_text:
            parts.append(moo_text)
        if tpart:
            parts.append(tpart)
        return " ".join(parts)
    if moo_text:
        return f"{moo_text} {tpart}".strip() if tpart else moo_text
    if tpart:
        return tpart
    return office_name or ""
