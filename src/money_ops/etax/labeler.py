"""normalized.json (フィールドコード保持) に mapping JSON を適用して label 付与。

mapping 解決:
- form_code (KOA020 等) で `mapping/<form_code>.json` を読込
- フィールドコード (ABA00010 等) → label/type/enum を取得
- 未解決コードは label=None で残す (情報損失なし)

出力形式 (labeled JSON):
- leaf 値: {"value": "令和6", "label": "年分", "type": "yy", "enum": "NENBUN", "code": "ABA00010"}
- 中間ノード: 階層維持
- 未解決コード: {"value": "...", "code": "...", "label": null}
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_MAPPING_DIR = Path(__file__).resolve().parent / "mapping"
_FIELD_CODE_RE = re.compile(r"^[A-Z]{2,4}\d{5}$")


@lru_cache(maxsize=256)
def load_mapping(form_code: str) -> dict:
    """mapping/<form_code>.json を読込。なければ空 dict。"""
    p = _MAPPING_DIR / f"{form_code}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _label_value(code: str, value: str, mapping: dict) -> dict:
    info = mapping.get("fields", {}).get(code)
    out = {"code": code, "value": value}
    if info:
        out["label"] = info.get("label")
        if info.get("type"):
            out["type"] = info["type"]
        if info.get("enum"):
            out["enum"] = info["enum"]
    else:
        out["label"] = None
    return out


def _walk(obj: Any, mapping: dict) -> Any:
    """階層 dict/list を再帰、leaf でフィールドコード判定したら label 付与。

    親キーがフィールドコードの場合 → leaf を {value, label, ...} に置換
    親キーが非コード (中間ノード等) → そのまま再帰
    """
    if isinstance(obj, dict):
        out: dict = {}
        for k, v in obj.items():
            if _FIELD_CODE_RE.match(k):
                # leaf 値 (str) or ネスト (dict/list) いずれも対象
                if isinstance(v, str):
                    out[k] = _label_value(k, v, mapping)
                else:
                    # ネスト (繰り返し行や intermediate group) は子供を再帰
                    sub = _walk(v, mapping)
                    info = mapping.get("fields", {}).get(k, {})
                    out[k] = {
                        "code": k,
                        "label": info.get("label"),
                        "children": sub,
                    }
            else:
                out[k] = _walk(v, mapping)
        return out
    if isinstance(obj, list):
        return [_walk(x, mapping) for x in obj]
    return obj


def apply_labels(normalized: dict) -> dict:
    """normalized.json (parser 出力) → labeled 構造に変換。"""
    out = {
        "schema_version": normalized.get("schema_version"),
        "tax_type": normalized.get("tax_type"),
        "form_version": normalized.get("form_version"),
        "source_file": normalized.get("source_file"),
        "header": normalized.get("header"),  # IT は ENUM 名で来るので別 mapping 系統 (本 issue 対象外)
        "forms": [],
        "attachments": [],
        "sofusho": normalized.get("sofusho"),
    }
    for f in normalized.get("forms", []):
        mapping = load_mapping(f["form_code"])
        out["forms"].append({
            "form_id": f["form_id"],
            "form_code": f["form_code"],
            "mapping_ver": mapping.get("_meta", {}).get("source_ver"),
            "fields": _walk(f["fields"], mapping),
        })
    for f in normalized.get("attachments", []):
        # 添付 (TEG158/700/830) の mapping は別系統 (ENUM 名)、本 issue では未対応
        out["attachments"].append({
            "form_id": f["form_id"],
            "form_code": f["form_code"],
            "mapping_ver": None,
            "fields": f["fields"],
        })
    return out


def coverage_stats(normalized: dict) -> dict:
    """mapping 解決率を集計。"""
    total = {"hit": 0, "miss": 0}
    by_form: dict = {}
    for f in normalized.get("forms", []):
        mapping = load_mapping(f["form_code"])
        codes_in_xtx: set = set()

        def collect(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if _FIELD_CODE_RE.match(k):
                        codes_in_xtx.add(k)
                    collect(v)
            elif isinstance(o, list):
                for x in o:
                    collect(x)

        collect(f["fields"])
        hit = sum(1 for c in codes_in_xtx if c in mapping.get("fields", {}))
        miss = len(codes_in_xtx) - hit
        by_form[f["form_id"]] = {"hit": hit, "miss": miss, "codes": len(codes_in_xtx)}
        total["hit"] += hit
        total["miss"] += miss
    return {"total": total, "by_form": by_form}
