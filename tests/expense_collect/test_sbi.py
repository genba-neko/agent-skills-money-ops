"""SBI 入出金明細（CSV）収集スクリプトのユニットテスト

conftest の skill 引数で expense-collect 配下を指定。
"""
from __future__ import annotations

from tests.conftest import build_collector, load_site_module

_CODE = "sbi"
_SKILL = "expense-collect"
_mod = load_site_module(_CODE, skill=_SKILL)
SBIExpenseCollector = _mod.SBIExpenseCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, SBIExpenseCollector, year, skill=_SKILL)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name.startswith("SBI証券")


def test_build_date_range_past_year(tmp_path):
    c = _make(tmp_path, year=2024)
    start, end = c._build_date_range()
    assert start == "2024/01/01"
    assert end == "2024/12/31"


def test_build_date_range_future_year_rejected(tmp_path):
    c = _make(tmp_path, year=2025)
    c.config["target_year"] = 9999
    import pytest
    with pytest.raises(ValueError, match="未来年"):
        c._build_date_range()
