"""nenkantorihikihokokusho.json の dict → nenkantorihikihokokusho.xml 生成モジュール

PDFのみ会社向け。json と同構造の XML を生成し source="pdf_generated" で識別する。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy


def _add(parent: ET.Element, tag: str, value) -> None:
    el = ET.SubElement(parent, tag)
    if isinstance(value, bool):
        el.text = "true" if value else "false"
    else:
        el.text = str(value)


def generate_xml_from_json(data: dict) -> str:
    """nenkantorihikihokokusho.json の dict から XML 文字列を生成する。

    source フィールドは "pdf_generated" に上書きされる。
    """
    d = deepcopy(data)
    d["source"] = "pdf_generated"

    root = ET.Element("nenkantorihikihokokusho")

    _add(root, "company", d.get("company", ""))
    _add(root, "code", d.get("code", ""))
    _add(root, "year", d.get("year", ""))
    _add(root, "document_type", d.get("document_type", ""))
    _add(root, "source", d["source"])

    # account
    acc_el = ET.SubElement(root, "account")
    acc = d.get("account", {})
    _add(acc_el, "口座種別", acc.get("口座種別", ""))
    _add(acc_el, "譲渡所得源泉徴収", acc.get("譲渡所得源泉徴収", False))
    _add(acc_el, "配当所得源泉徴収", acc.get("配当所得源泉徴収", False))
    _add(acc_el, "開設日", acc.get("開設日", ""))

    # 譲渡
    joto = d.get("譲渡", {})
    joto_el = ET.SubElement(root, "譲渡")
    _add(joto_el, "取引件数_上場株式等", joto.get("取引件数_上場株式等", 0))
    _add(joto_el, "取引件数_信用等", joto.get("取引件数_信用等", 0))
    _add(joto_el, "取引件数_一般株式等", joto.get("取引件数_一般株式等", 0))

    for section in ("上場株式等", "一般株式等"):
        sec = joto.get(section, {})
        sec_el = ET.SubElement(joto_el, section)
        _add(sec_el, "譲渡の対価の額", sec.get("譲渡の対価の額", 0))
        _add(sec_el, "取得費及び譲渡に要した費用の額等", sec.get("取得費及び譲渡に要した費用の額等", 0))
        _add(sec_el, "差引金額_譲渡損益", sec.get("差引金額_譲渡損益", 0))

    son = joto.get("損益通算後", {})
    son_el = ET.SubElement(joto_el, "損益通算後")
    _add(son_el, "所得控除の額の合計額", son.get("所得控除の額の合計額", 0))
    _add(son_el, "差引所得税額", son.get("差引所得税額", 0))
    _add(son_el, "翌年繰越損失額", son.get("翌年繰越損失額", 0))

    gokei = joto.get("合計", {})
    gokei_el = ET.SubElement(joto_el, "合計")
    _add(gokei_el, "課税標準", gokei.get("課税標準", 0))
    _add(gokei_el, "取得費等", gokei.get("取得費等", 0))
    _add(gokei_el, "差引損益", gokei.get("差引損益", 0))

    # 配当等
    div = d.get("配当等", {})
    div_el = ET.SubElement(root, "配当等")
    for section in (
        "上場株式の配当等",
        "特定株式投資信託の収益の分配等",
        "一般株式等の配当等",
        "投資信託等の収益の分配等",
        "非居住者等への配当等",
    ):
        sec = div.get(section, {})
        sec_el = ET.SubElement(div_el, section)
        _add(sec_el, "配当等の額", sec.get("配当等の額", 0))
        _add(sec_el, "所得税", sec.get("所得税", 0))
        _add(sec_el, "復興特別所得税", sec.get("復興特別所得税", 0))
        _add(sec_el, "地方税", sec.get("地方税", 0))

    gai = div.get("外国株式等の配当等", {})
    gai_el = ET.SubElement(div_el, "外国株式等の配当等")
    _add(gai_el, "配当等の額", gai.get("配当等の額", 0))
    _add(gai_el, "外国所得税", gai.get("外国所得税", 0))

    nisa_div = div.get("NISA口座内の配当等", {})
    nisa_div_el = ET.SubElement(div_el, "NISA口座内の配当等")
    _add(nisa_div_el, "配当等の額", nisa_div.get("配当等の額", 0))

    total_div = div.get("合計", {})
    total_el = ET.SubElement(div_el, "合計")
    _add(total_el, "配当等の額", total_div.get("配当等の額", 0))
    _add(total_el, "所得税_源泉徴収税額", total_div.get("所得税_源泉徴収税額", 0))
    _add(total_el, "復興特別所得税", total_div.get("復興特別所得税", 0))
    _add(total_el, "地方税", total_div.get("地方税", 0))
    _add(total_el, "納付税額", total_div.get("納付税額", 0))

    # NISA
    nisa = d.get("NISA", {}).get("譲渡等", {})
    nisa_el = ET.SubElement(root, "NISA")
    joto_nisa_el = ET.SubElement(nisa_el, "譲渡等")
    _add(joto_nisa_el, "譲渡の対価の額", nisa.get("譲渡の対価の額", 0))
    _add(joto_nisa_el, "取得費等", nisa.get("取得費等", 0))

    # 源泉徴収税額合計
    gen = d.get("源泉徴収税額合計", {})
    gen_el = ET.SubElement(root, "源泉徴収税額合計")
    _add(gen_el, "所得税", gen.get("所得税", 0))
    _add(gen_el, "復興特別所得税", gen.get("復興特別所得税", 0))

    # 証券会社
    co = d.get("証券会社", {})
    co_el = ET.SubElement(root, "証券会社")
    _add(co_el, "名称", co.get("名称", ""))
    _add(co_el, "法人番号", co.get("法人番号", ""))

    # raw_files
    raw_el = ET.SubElement(root, "raw_files")
    for f in d.get("raw_files", []):
        _add(raw_el, "file", f)

    _add(root, "collected_at", d.get("collected_at", ""))

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
