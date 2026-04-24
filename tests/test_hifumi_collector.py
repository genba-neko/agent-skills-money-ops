"""ひふみ投信 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import build_collector, load_site_module

_CODE = "hifumi"
_mod = load_site_module(_CODE)
HifumiCollector = _mod.HifumiCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, HifumiCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "ひふみ投信"


def test_year_month_patterns():
    patterns = _mod._year_month_patterns(2025)
    assert "2025/12" in patterns
    assert "2026/01" in patterns


def test_wait_for_login_returns_page2(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    page.get_by_role.return_value.count.return_value = 0
    page2 = MagicMock()
    popup_cm = MagicMock()
    popup_cm.__enter__ = MagicMock(return_value=MagicMock(value=page2))
    popup_cm.__exit__ = MagicMock(return_value=False)
    page.expect_popup.return_value = popup_cm

    with patch.object(_mod, "_wait"), patch("builtins.input", return_value=""):
        result = c._wait_for_login(page)

    page.goto.assert_called_once_with(c.config["login_url"])
    assert result is page2


def test_find_date_button_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page2 = MagicMock()
    page2.get_by_role.return_value.filter.return_value.count.return_value = 0
    result = c._find_date_button(page2, 2025)
    assert result is None


def test_collect_skip_when_date_button_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()
    page2 = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_wait_for_login", return_value=page1), \
         patch.object(c, "_navigate_to_eshishobako", return_value=page2), \
         patch.object(c, "_find_date_button", return_value=None), \
         patch.object(c, "log_result") as mock_log:
        c.run()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "skip"


def test_collect_error_when_pdf_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()
    page2 = MagicMock()
    date_btn = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_wait_for_login", return_value=page1), \
         patch.object(c, "_navigate_to_eshishobako", return_value=page2), \
         patch.object(c, "_find_date_button", return_value=date_btn), \
         patch.object(c, "_open_report_detail", return_value=True), \
         patch.object(c, "prepare_directory"), \
         patch.object(_mod, "capture_dpaw_pdf", return_value=None), \
         patch.object(c, "log_result") as mock_log:
        c.run()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "error"
