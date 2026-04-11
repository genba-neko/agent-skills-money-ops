"""TEG204 XML（e-Tax 特定口座年間取引報告書）→ nenkantorihikihokokusho.json 変換モジュール"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

_ACCOUNT_KIND_MAP = {
    "1": "源泉徴収あり特定口座",
    "2": "源泉徴収なし特定口座",
}


def _text(root: ET.Element, tag: str, default: str = "0") -> str:
    el = root.find(tag)
    return el.text.strip() if el is not None and el.text else default


def _int(root: ET.Element, tag: str) -> int:
    return int(_text(root, tag, "0"))


def _date(yyyymmdd: str) -> str:
    """YYYYMMDD → YYYY-MM-DD"""
    if len(yyyymmdd) == 8:
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd


def convert_teg204_xml(
    xml_path: str | Path,
    company: str,
    code: str,
    year: int,
    raw_files: list[str] | None = None,
    collected_at: str | None = None,
) -> dict:
    """TEG204 XML を nenkantorihikihokokusho.json の dict に変換する。

    Parameters
    ----------
    xml_path:
        TEG204 XML ファイルのパス
    company:
        証券会社名（registry.json の name）
    code:
        証券会社コード（registry.json の code）
    year:
        対象年度（例: 2025）
    raw_files:
        収集した原本ファイルのパスリスト
    collected_at:
        収集日時（ISO 8601 形式）。None の場合は現在日時を使用
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    account_kind_code = _text(root, "ZLE010", "1")
    account_kind = _ACCOUNT_KIND_MAP.get(account_kind_code, account_kind_code)
    kasetsu_raw = _text(root, "ZLE040", "")
    kasetsu = _date(kasetsu_raw) if kasetsu_raw else ""

    return {
        "company": company,
        "code": code,
        "year": year,
        "document_type": "特定口座年間取引報告書",
        "source": "xml",
        "account": {
            "口座種別": account_kind,
            "譲渡所得源泉徴収": _int(root, "ZLE020") == 1,
            "配当所得源泉徴収": _int(root, "ZLE030") == 1,
            "開設日": kasetsu,
        },
        "譲渡": {
            "取引件数_上場株式等": _int(root, "ZLH010"),
            "取引件数_信用等": _int(root, "ZLH020"),
            "取引件数_一般株式等": _int(root, "ZLH030"),
            "上場株式等": {
                "譲渡の対価の額": _int(root, "ZLH040"),
                "取得費及び譲渡に要した費用の額等": _int(root, "ZLH050"),
                "差引金額_譲渡損益": _int(root, "ZLH060"),
            },
            "一般株式等": {
                "譲渡の対価の額": _int(root, "ZLH070"),
                "取得費及び譲渡に要した費用の額等": _int(root, "ZLH080"),
                "差引金額_譲渡損益": _int(root, "ZLH090"),
            },
            "損益通算後": {
                "所得控除の額の合計額": _int(root, "ZLH100"),
                "差引所得税額": _int(root, "ZLH110"),
                "翌年繰越損失額": _int(root, "ZLH120"),
            },
            "合計": {
                "課税標準": _int(root, "ZLH130"),
                "取得費等": _int(root, "ZLH140"),
                "差引損益": _int(root, "ZLH150"),
            },
        },
        "配当等": {
            "上場株式の配当等": {
                "配当等の額": _int(root, "ZLI010"),
                "所得税": _int(root, "ZLI020"),
                "復興特別所得税": _int(root, "ZLI030"),
                "地方税": _int(root, "ZLI040"),
            },
            "特定株式投資信託の収益の分配等": {
                "配当等の額": _int(root, "ZLI050"),
                "所得税": _int(root, "ZLI060"),
                "復興特別所得税": _int(root, "ZLI070"),
                "地方税": _int(root, "ZLI080"),
            },
            "一般株式等の配当等": {
                "配当等の額": _int(root, "ZLI090"),
                "所得税": _int(root, "ZLI100"),
                "復興特別所得税": _int(root, "ZLI110"),
                "地方税": _int(root, "ZLI120"),
            },
            "投資信託等の収益の分配等": {
                "配当等の額": _int(root, "ZLI130"),
                "所得税": _int(root, "ZLI140"),
                "復興特別所得税": _int(root, "ZLI150"),
                "地方税": _int(root, "ZLI160"),
            },
            "非居住者等への配当等": {
                "配当等の額": _int(root, "ZLI170"),
                "所得税": _int(root, "ZLI180"),
                "復興特別所得税": _int(root, "ZLI190"),
                "地方税": _int(root, "ZLI200"),
            },
            "外国株式等の配当等": {
                "配当等の額": _int(root, "ZLI210"),
                "外国所得税": _int(root, "ZLI220"),
            },
            "NISA口座内の配当等": {
                "配当等の額": _int(root, "ZLI230"),
            },
            "合計": {
                "配当等の額": _int(root, "ZLI240"),
                "所得税_源泉徴収税額": _int(root, "ZLI250"),
                "復興特別所得税": _int(root, "ZLI260"),
                "地方税": _int(root, "ZLI270"),
                "納付税額": _int(root, "ZLI280"),
            },
        },
        "NISA": {
            "譲渡等": {
                "譲渡の対価の額": _int(root, "ZLJ010"),
                "取得費等": _int(root, "ZLJ020"),
            },
        },
        "源泉徴収税額合計": {
            "所得税": _int(root, "ZLK010"),
            "復興特別所得税": _int(root, "ZLK020"),
        },
        "証券会社": {
            "名称": _text(root, "ZLF010"),
            "法人番号": _text(root, "ZLF020"),
        },
        "raw_files": raw_files or [],
        "collected_at": collected_at or datetime.now().isoformat(),
    }
