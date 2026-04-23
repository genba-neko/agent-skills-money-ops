"""大和CONNECT証券 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from tests.conftest import build_collector, load_site_module

_CODE = "daiwa-connect"
_mod = load_site_module(_CODE)
DaiwaConnectCollector = _mod.DaiwaConnectCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, DaiwaConnectCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "大和コネクト証券"


def test_login_first_goto_is_login_url(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    # セッション有効 → webbroker3 へリダイレクト済みを想定
    page.url = "https://www.connect-sec.co.jp/webbroker3/top"

    with patch.object(_mod, "_wait"):
        result = c._login(page)

    # 最初の goto が LOGIN_URL であること
    assert page.goto.call_args_list[0] == call(_mod._LOGIN_URL)
    assert result is page


def test_collect_error_when_pdf_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()
    page2 = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_login", return_value=page1), \
         patch.object(c, "_open_electronic_delivery", return_value=page2), \
         patch.object(c, "_navigate_to_annual_report"), \
         patch.object(c, "_download_pdf_via_route", return_value=None), \
         patch.object(c, "log_result") as mock_log:
        c.collect()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "error"


def test_collect_success_flow(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()
    page1 = MagicMock()
    page2 = MagicMock()
    pdf_path = str(tmp_path / "raw" / "report.pdf")

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_login", return_value=page1), \
         patch.object(c, "_open_electronic_delivery", return_value=page2), \
         patch.object(c, "_navigate_to_annual_report"), \
         patch.object(c, "_download_pdf_via_route", return_value=pdf_path), \
         patch.object(_mod, "convert_pdf_to_json", return_value={"code": _CODE}), \
         patch.object(c, "log_result") as mock_log:
        c.collect()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "success"
