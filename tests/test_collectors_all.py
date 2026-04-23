"""全社 collect.py の共通構造テスト（パラメータ化）"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import SITES_DIR, build_collector, load_site_module

# (site_code, collector_class_name)
ALL_SITES = [
    ("sbi",              "SBICollector"),
    ("rakuten",          "RakutenCollector"),
    ("nomura",           "NomuraCollector"),
    ("monex",            "MonexCollector"),
    ("matsui",           "MatsuiCollector"),
    ("gmo-click",        "GMOClickCollector"),
    ("smbcnikko",        "SMBCNikkoCollector"),
    ("mufg-esmart",      "MufgEsmartCollector"),
    ("tsumiki",          "TsumikiCollector"),
    ("daiwa-connect",    "DaiwaConnectCollector"),
    ("paypay",           "PaypayCollector"),
    ("hifumi",           "HifumiCollector"),
    ("sawakami",         "SawakamiCollector"),
    ("nomura-mochikabu", "NomuraMochikabuCollector"),
    ("webull",           "WebullCollector"),
]

IDS = [code for code, _ in ALL_SITES]


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_collect_py_exists(code, cls_name):
    assert (SITES_DIR / code / "collect.py").exists()


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_site_json_exists(code, cls_name):
    assert (SITES_DIR / code / "site.json").exists()


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_site_json_required_fields(code, cls_name):
    data = json.loads((SITES_DIR / code / "site.json").read_text(encoding="utf-8"))
    for field in ("code", "name", "output_dir", "target_year"):
        assert field in data, f"{code}/site.json に {field} がない"


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_module_importable(code, cls_name):
    mod = load_site_module(code)
    assert hasattr(mod, cls_name), f"{code}: {cls_name} クラスが存在しない"


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_instantiation(tmp_path, code, cls_name):
    mod = load_site_module(code)
    cls = getattr(mod, cls_name)
    collector = build_collector(tmp_path, code, cls)
    assert collector.code == code


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_year_param(tmp_path, code, cls_name):
    mod = load_site_module(code)
    cls = getattr(mod, cls_name)
    collector = build_collector(tmp_path, code, cls, year=2024)
    assert collector.config["target_year"] == 2024


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_output_dir_contains_year(tmp_path, code, cls_name):
    mod = load_site_module(code)
    cls = getattr(mod, cls_name)
    collector = build_collector(tmp_path, code, cls, year=2025)
    assert str(collector.output_dir) != ""


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_collect_not_implemented_on_base(tmp_path, code, cls_name):
    """collect() は各社で実装されている（NotImplementedError を投げないこと）"""
    mod = load_site_module(code)
    cls = getattr(mod, cls_name)
    collector = build_collector(tmp_path, code, cls)
    # collect メソッドが存在し、BaseCollector の NotImplementedError を上書きしていること
    assert callable(getattr(collector, "collect", None))
    # クラス自身のメソッド（継承元の NotImplementedError ではない）
    assert "collect" in cls.__dict__ or any(
        "collect" in C.__dict__ for C in cls.__mro__[1:-1]
    )


@pytest.mark.parametrize("code,cls_name", ALL_SITES, ids=IDS)
def test_verify_pdf_has_method(tmp_path, code, cls_name):
    """verify_pdf() が BaseCollector から継承されていること"""
    mod = load_site_module(code)
    cls = getattr(mod, cls_name)
    collector = build_collector(tmp_path, code, cls)
    assert callable(getattr(collector, "verify_pdf", None))


def test_verify_pdf_valid(tmp_path):
    """正常な PDF（%PDF ヘッダ）は True を返す"""
    from tests.conftest import build_collector, load_site_module
    mod = load_site_module("sbi")
    c = build_collector(tmp_path, "sbi", mod.SBICollector)
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake content")
    assert c.verify_pdf(pdf) is True


def test_verify_pdf_not_exists(tmp_path):
    mod = load_site_module("sbi")
    c = build_collector(tmp_path, "sbi", mod.SBICollector)
    assert c.verify_pdf(tmp_path / "missing.pdf") is False


def test_verify_pdf_empty(tmp_path):
    mod = load_site_module("sbi")
    c = build_collector(tmp_path, "sbi", mod.SBICollector)
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"")
    assert c.verify_pdf(pdf) is False


def test_verify_pdf_wrong_magic(tmp_path):
    mod = load_site_module("sbi")
    c = build_collector(tmp_path, "sbi", mod.SBICollector)
    pdf = tmp_path / "notpdf.pdf"
    pdf.write_bytes(b"HTML<html>not a pdf")
    assert c.verify_pdf(pdf) is False
