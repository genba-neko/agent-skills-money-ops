from pathlib import Path

import pytest

from money_ops.converter import convert_teg204_xml

SAMPLE_XML = Path(__file__).resolve().parents[1] / "fixtures" / "teg204_sample.xml"

_NS_K = "http://xml.e-tax.nta.go.jp/XSD/kyotsu"


@pytest.fixture
def result():
    return convert_teg204_xml(
        SAMPLE_XML,
        company="サンプル証券",
        code="sample",
        year=2025,
        raw_files=["raw/2025_nentori.xml"],
        collected_at="2026-04-11T00:00:00",
    )


def test_top_level_fields(result):
    assert result["company"] == "サンプル証券"
    assert result["code"] == "sample"
    assert result["year"] == 2025
    assert result["document_type"] == "特定口座年間取引報告書"
    assert result["source"] == "xml"


def test_account(result):
    acc = result["account"]
    assert acc["口座種別"] == "源泉徴収あり特定口座"
    assert acc["譲渡所得源泉徴収"] is True
    assert acc["配当所得源泉徴収"] is True
    assert acc["開設日"] == "2010-03-10"


def test_譲渡_取引件数(result):
    t = result["譲渡"]
    assert t["取引件数_上場株式等"] == 10
    assert t["取引件数_信用等"] == 5
    assert t["取引件数_一般株式等"] == 0


def test_譲渡_上場株式等(result):
    joto = result["譲渡"]["上場株式等"]
    assert joto["譲渡の対価の額"] == 1000000
    assert joto["取得費及び譲渡に要した費用の額等"] == 900000
    assert joto["差引金額_譲渡損益"] == 100000


def test_譲渡_合計(result):
    total = result["譲渡"]["合計"]
    assert total["課税標準"] == 1000000
    assert total["取得費等"] == 900000
    assert total["差引損益"] == 100000


def test_配当等_上場株式(result):
    div = result["配当等"]["上場株式の配当等"]
    assert div["配当等の額"] == 50000
    assert div["所得税"] == 7655
    assert div["復興特別所得税"] == 2499
    assert div["地方税"] == 0


def test_配当等_特定株式投信(result):
    div = result["配当等"]["特定株式投資信託の収益の分配等"]
    assert div["配当等の額"] == 20000
    assert div["所得税"] == 3064
    assert div["復興特別所得税"] == 998


def test_配当等_合計(result):
    total = result["配当等"]["合計"]
    assert total["配当等の額"] == 70000
    assert total["所得税_源泉徴収税額"] == 10719
    assert total["復興特別所得税"] == 3497
    assert total["地方税"] == 0
    assert total["外国税"] == 0


def test_nisa(result):
    nisa = result["NISA"]["譲渡等"]
    assert nisa["譲渡の対価の額"] == 0
    assert nisa["取得費等"] == 0


def test_源泉徴収税額合計(result):
    tax = result["源泉徴収税額合計"]
    assert tax["所得税"] == 18374
    assert tax["復興特別所得税"] == 5996


def test_raw_files(result):
    assert result["raw_files"] == ["raw/2025_nentori.xml"]


def test_collected_at(result):
    assert result["collected_at"] == "2026-04-11T00:00:00"


def test_missing_elements_default_zero(tmp_path):
    """必須でない要素が欠けていても 0 にフォールバックする（最小 TEG204 XML）"""
    minimal_xml = tmp_path / "minimal.xml"
    minimal_xml.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<TEG204 xmlns="{_NS_K}" VR="1.0" id="TEST" page="1"'
        f' sakuseiDay="2026-01-01" sakuseiNM="test" softNM="test">'
        f"</TEG204>",
        encoding="utf-8",
    )
    r = convert_teg204_xml(minimal_xml, company="テスト証券", code="test", year=2025)
    assert r["account"]["口座種別"] == "源泉徴収あり特定口座"
    assert r["account"]["譲渡所得源泉徴収"] is False
    assert r["譲渡"]["取引件数_上場株式等"] == 0
    assert r["配当等"]["合計"]["配当等の額"] == 0
    assert r["源泉徴収税額合計"]["所得税"] == 0
