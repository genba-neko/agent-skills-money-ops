"""TEG204 XML（e-Tax 特定口座年間取引報告書）→ nenkantorihikihokokusho.json 変換モジュール

e-Tax 標準フォーマット TEG204 の名前空間付き XML を解析する。
ルート要素: {http://xml.e-tax.nta.go.jp/XSD/kyotsu}TEG204

主要グループ:
  ZLE00000 : 口座/顧客情報
  ZLF00000 : 財務データ（譲渡・配当等・NISA・源泉徴収税額）
  ZLG00000 / ZLH00000 : 証券会社情報（会社により異なる）
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

_NS_K = "http://xml.e-tax.nta.go.jp/XSD/kyotsu"
_NS_G = "http://xml.e-tax.nta.go.jp/XSD/general"
_K = f"{{{_NS_K}}}"
_G = f"{{{_NS_G}}}"

_ACCOUNT_KIND_MAP = {
    "1": "源泉徴収あり特定口座",
    "2": "源泉徴収なし特定口座",
}

# 元号ベース年 (元号N年 = BASE + N)
_ERA_BASE: dict[int, int] = {1: 1867, 2: 1911, 3: 1925, 4: 1988, 5: 2018}


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------

def _find(root: ET.Element | None, *tags: str) -> ET.Element | None:
    """NS_K 名前空間で path を順に辿って要素を返す。途中が None なら None。"""
    el = root
    for tag in tags:
        if el is None:
            return None
        el = el.find(_K + tag)
    return el


def _ktext(root: ET.Element | None, *tags: str, default: str = "0") -> str:
    el = _find(root, *tags)
    return el.text.strip() if el is not None and el.text and el.text.strip() else default


def _kint(root: ET.Element | None, *tags: str) -> int:
    return int(_ktext(root, *tags, default="0"))


def _kubun(root: ET.Element | None, *tags: str) -> str | None:
    """path を辿った末尾要素の子 kubun_CD のテキストを返す。"""
    el = _find(root, *tags)
    if el is None:
        return None
    kubun = el.find(_K + "kubun_CD")
    return kubun.text.strip() if kubun is not None and kubun.text else None


def _gdate(el: ET.Element | None) -> str:
    """{NS_G}era / yy / mm / dd 子要素を持つ要素から YYYY-MM-DD 文字列を返す。"""
    if el is None:
        return ""
    era = el.findtext(_G + "era")
    yy = el.findtext(_G + "yy")
    mm = el.findtext(_G + "mm")
    dd = el.findtext(_G + "dd")
    if not (era and yy):
        return ""
    year = _ERA_BASE.get(int(era), 0) + int(yy)
    if mm and dd:
        return f"{year:04d}-{int(mm):02d}-{int(dd):02d}"
    return str(year)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

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
        証券会社名（site.json の name）
    code:
        証券会社コード（site.json の code）
    year:
        対象年度（例: 2025）
    raw_files:
        収集した原本ファイルのパスリスト
    collected_at:
        収集日時（ISO 8601 形式）。None の場合は現在日時を使用
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # ---- 口座情報 (ZLE00000) ----
    zle = root.find(_K + "ZLE00000")
    account_kind_code = _kubun(zle, "ZLE00120") or "1"
    account_kind = _ACCOUNT_KIND_MAP.get(account_kind_code, account_kind_code)
    joto_gensen = _kubun(zle, "ZLE00070", "ZLE00080") == "1"
    haitou_gensen = _kubun(zle, "ZLE00070", "ZLE00090") == "1"
    kasetsu = _gdate(_find(zle, "ZLE00110"))

    # ---- 財務データ (ZLF00000) ----
    zlf = root.find(_K + "ZLF00000")
    zlf010 = _find(zlf, "ZLF00010")   # 譲渡セクション
    zlf190 = _find(zlf, "ZLF00190")   # 配当等セクション

    def fi(*tags: str) -> int:
        """ZLF00010 配下のパスから int を返す。"""
        return _kint(zlf010, *tags) if zlf010 is not None else 0

    def fd(*tags: str) -> int:
        """ZLF00190 配下のパスから int を返す。"""
        return _kint(zlf190, *tags) if zlf190 is not None else 0

    return {
        "company": company,
        "code": code,
        "year": year,
        "document_type": "特定口座年間取引報告書",
        "source": "xml",
        "account": {
            "口座種別": account_kind,
            "譲渡所得源泉徴収": joto_gensen,
            "配当所得源泉徴収": haitou_gensen,
            "開設日": kasetsu,
        },
        "譲渡": {
            "取引件数_上場株式等": fi("ZLF00020"),
            "取引件数_信用等": fi("ZLF00030"),
            "取引件数_一般株式等": fi("ZLF00040"),
            "上場株式等": {
                "譲渡の対価の額": fi("ZLF00050", "ZLF00060"),
                "取得費及び譲渡に要した費用の額等": fi("ZLF00050", "ZLF00080"),
                "差引金額_譲渡損益": fi("ZLF00050", "ZLF00100"),
            },
            "一般株式等": {
                "譲渡の対価の額": fi("ZLF00110", "ZLF00120"),
                "取得費及び譲渡に要した費用の額等": fi("ZLF00110", "ZLF00130"),
                "差引金額_譲渡損益": fi("ZLF00110", "ZLF00140"),
            },
            "合計": {
                "課税標準": fi("ZLF00150", "ZLF00160"),
                "取得費等": fi("ZLF00150", "ZLF00170"),
                "差引損益": fi("ZLF00150", "ZLF00180"),
            },
        },
        "配当等": {
            "上場株式の配当等": {
                "配当等の額": fd("ZLF00200", "ZLF00210"),
                "所得税": fd("ZLF00200", "ZLF00220"),
                "復興特別所得税": fd("ZLF00200", "ZLF00230"),
                "地方税": fd("ZLF00200", "ZLF00240"),
            },
            "特定株式投資信託の収益の分配等": {
                "配当等の額": fd("ZLF00250", "ZLF00260"),
                "所得税": fd("ZLF00250", "ZLF00270"),
                "復興特別所得税": fd("ZLF00250", "ZLF00280"),
                "地方税": fd("ZLF00250", "ZLF00290"),
            },
            "一般株式等の配当等": {
                "配当等の額": fd("ZLF00300", "ZLF00310"),
                "所得税": fd("ZLF00300", "ZLF00320"),
                "復興特別所得税": fd("ZLF00300", "ZLF00330"),
                "地方税": fd("ZLF00300", "ZLF00340"),
            },
            "投資信託等の収益の分配等": {
                "配当等の額": fd("ZLF00350", "ZLF00360"),
                "所得税": fd("ZLF00350", "ZLF00370"),
                "復興特別所得税": fd("ZLF00350", "ZLF00380"),
                "地方税": fd("ZLF00350", "ZLF00390"),
            },
            "外国株式等の配当等": {
                "配当等の額": fd("ZLF00410", "ZLF00420"),
                "所得税": fd("ZLF00410", "ZLF00430"),
                "復興特別所得税": fd("ZLF00410", "ZLF00440"),
                "外国所得税": fd("ZLF00410", "ZLF00450"),
            },
            "合計": {
                "配当等の額": fd("ZLF00460", "ZLF00470"),
                "所得税_源泉徴収税額": fd("ZLF00460", "ZLF00480"),
                "復興特別所得税": fd("ZLF00460", "ZLF00490"),
                "地方税": fd("ZLF00460", "ZLF00500"),
                "外国税": fd("ZLF00460", "ZLF00520"),
            },
        },
        "NISA": {
            "譲渡等": {
                "譲渡の対価の額": fd("ZLF00900", "ZLF00910"),
                "取得費等": fd("ZLF00900", "ZLF00920"),
            },
        },
        "源泉徴収税額合計": {
            "所得税": fd("ZLF00870", "ZLF00880"),
            "復興特別所得税": fd("ZLF00870", "ZLF00890"),
        },
        "raw_files": raw_files or [],
        "collected_at": collected_at or datetime.now().isoformat(),
    }
