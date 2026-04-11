from pathlib import Path

import pytest

from money_ops.converter import convert_teg204_xml

SAMPLE_XML = Path(__file__).parent / "fixtures" / "teg204_sample.xml"


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


def test_譲渡_損益通算後(result):
    tsu = result["譲渡"]["損益通算後"]
    assert tsu["所得控除の額の合計額"] == 0
    assert tsu["差引所得税額"] == 10000
    assert tsu["翌年繰越損失額"] == 0


def test_配当等_上場株式(result):
    div = result["配当等"]["上場株式の配当等"]
    assert div["配当等の額"] == 50000
    assert div["所得税"] == 7655
    assert div["復興特別所得税"] == 2499
    assert div["地方税"] == 0


def test_配当等_合計(result):
    total = result["配当等"]["合計"]
    assert total["配当等の額"] == 270100
    assert total["所得税_源泉徴収税額"] == 41360
    assert total["復興特別所得税"] == 13490
    assert total["地方税"] == 20010
    assert total["納付税額"] == 20010


def test_nisa(result):
    nisa = result["NISA"]["譲渡等"]
    assert nisa["譲渡の対価の額"] == 0
    assert nisa["取得費等"] == 0


def test_源泉徴収税額合計(result):
    tax = result["源泉徴収税額合計"]
    assert tax["所得税"] == 41360
    assert tax["復興特別所得税"] == 13490


def test_証券会社(result):
    co = result["証券会社"]
    assert co["名称"] == "サンプル証券株式会社"
    assert co["法人番号"] == "1234567890123"


def test_raw_files(result):
    assert result["raw_files"] == ["raw/2025_nentori.xml"]


def test_collected_at(result):
    assert result["collected_at"] == "2026-04-11T00:00:00"


def test_missing_elements_default_zero(tmp_path):
    """必須でない要素が欠けていても 0 にフォールバックする"""
    minimal_xml = tmp_path / "minimal.xml"
    minimal_xml.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<BZL030010>"
        "<ZLF010>テスト証券</ZLF010>"
        "<ZLE010>2</ZLE010>"
        "</BZL030010>",
        encoding="utf-8",
    )
    result = convert_teg204_xml(minimal_xml, company="テスト証券", code="test", year=2025)
    assert result["account"]["口座種別"] == "源泉徴収なし特定口座"
    assert result["譲渡"]["取引件数_上場株式等"] == 0
    assert result["配当等"]["合計"]["配当等の額"] == 0
