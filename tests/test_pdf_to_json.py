import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from money_ops.converter import convert_pdf_to_json, generate_xml_from_json

DUMMY_PDF = Path(__file__).parent / "fixtures" / "dummy.pdf"

_EXTRACTED = {
    "account": {
        "口座種別": "源泉徴収あり特定口座",
        "譲渡所得源泉徴収": True,
        "配当所得源泉徴収": True,
        "開設日": "2015-04-01",
    },
    "譲渡": {
        "取引件数_上場株式等": 3,
        "取引件数_信用等": 0,
        "取引件数_一般株式等": 0,
        "上場株式等": {
            "譲渡の対価の額": 300000,
            "取得費及び譲渡に要した費用の額等": 250000,
            "差引金額_譲渡損益": 50000,
        },
        "一般株式等": {
            "譲渡の対価の額": 0,
            "取得費及び譲渡に要した費用の額等": 0,
            "差引金額_譲渡損益": 0,
        },
        "損益通算後": {
            "所得控除の額の合計額": 0,
            "差引所得税額": 5000,
            "翌年繰越損失額": 0,
        },
        "合計": {
            "課税標準": 300000,
            "取得費等": 250000,
            "差引損益": 50000,
        },
    },
    "配当等": {
        "上場株式の配当等": {
            "配当等の額": 10000,
            "所得税": 1531,
            "復興特別所得税": 499,
            "地方税": 0,
        },
        "特定株式投資信託の収益の分配等": {
            "配当等の額": 0,
            "所得税": 0,
            "復興特別所得税": 0,
            "地方税": 0,
        },
        "一般株式等の配当等": {
            "配当等の額": 0,
            "所得税": 0,
            "復興特別所得税": 0,
            "地方税": 0,
        },
        "投資信託等の収益の分配等": {
            "配当等の額": 0,
            "所得税": 0,
            "復興特別所得税": 0,
            "地方税": 0,
        },
        "非居住者等への配当等": {
            "配当等の額": 0,
            "所得税": 0,
            "復興特別所得税": 0,
            "地方税": 0,
        },
        "外国株式等の配当等": {"配当等の額": 0, "外国所得税": 0},
        "NISA口座内の配当等": {"配当等の額": 0},
        "合計": {
            "配当等の額": 10000,
            "所得税_源泉徴収税額": 1531,
            "復興特別所得税": 499,
            "地方税": 0,
            "納付税額": 0,
        },
    },
    "NISA": {"譲渡等": {"譲渡の対価の額": 0, "取得費等": 0}},
    "源泉徴収税額合計": {"所得税": 1531, "復興特別所得税": 499},
    "証券会社": {"名称": "テスト証券株式会社", "法人番号": "9876543210123"},
}


@pytest.fixture
def mock_client():
    client = MagicMock()
    message = MagicMock()
    message.content = [MagicMock(text=json.dumps(_EXTRACTED))]
    client.messages.create.return_value = message
    return client


@pytest.fixture
def result(tmp_path, mock_client):
    pdf = tmp_path / "dummy.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    return convert_pdf_to_json(
        pdf,
        company="テスト証券",
        code="test",
        year=2025,
        raw_files=["raw/2025_report.pdf"],
        collected_at="2026-04-11T00:00:00",
        client=mock_client,
    )


def test_top_level_fields(result):
    assert result["company"] == "テスト証券"
    assert result["code"] == "test"
    assert result["year"] == 2025
    assert result["document_type"] == "特定口座年間取引報告書"
    assert result["source"] == "pdf_ocr"


def test_account(result):
    acc = result["account"]
    assert acc["口座種別"] == "源泉徴収あり特定口座"
    assert acc["譲渡所得源泉徴収"] is True
    assert acc["開設日"] == "2015-04-01"


def test_譲渡(result):
    joto = result["譲渡"]["上場株式等"]
    assert joto["譲渡の対価の額"] == 300000
    assert joto["差引金額_譲渡損益"] == 50000


def test_配当等(result):
    div = result["配当等"]["上場株式の配当等"]
    assert div["配当等の額"] == 10000
    assert div["所得税"] == 1531


def test_raw_files(result):
    assert result["raw_files"] == ["raw/2025_report.pdf"]


def test_collected_at(result):
    assert result["collected_at"] == "2026-04-11T00:00:00"


def test_api_called_once(tmp_path, mock_client):
    pdf = tmp_path / "dummy.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    convert_pdf_to_json(pdf, company="テスト証券", code="test", year=2025, client=mock_client)
    mock_client.messages.create.assert_called_once()


def test_api_uses_correct_model(tmp_path, mock_client):
    pdf = tmp_path / "dummy.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    convert_pdf_to_json(pdf, company="テスト証券", code="test", year=2025, client=mock_client)
    call_kwargs = mock_client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"


# --- generate_xml_from_json テスト ---

@pytest.fixture
def xml_result(result):
    return generate_xml_from_json(result)


def test_xml_is_string(xml_result):
    assert isinstance(xml_result, str)
    assert xml_result.startswith("<?xml")


def test_xml_source_is_pdf_generated(xml_result):
    import xml.etree.ElementTree as ET
    tree = ET.fromstring(xml_result.split("\n", 1)[1])
    assert tree.find("source").text == "pdf_generated"


def test_xml_original_source_unchanged(result):
    assert result["source"] == "pdf_ocr"


def test_xml_contains_company(xml_result):
    assert "テスト証券" in xml_result


def test_xml_contains_amount(xml_result):
    assert "300000" in xml_result


def test_xml_raw_files(xml_result):
    assert "2025_report.pdf" in xml_result
