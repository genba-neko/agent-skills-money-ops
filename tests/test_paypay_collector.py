"""PayPay証券 収集スクリプトのユニットテスト（Playwright モック）"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import build_collector, load_site_module

_CODE = "paypay"
_mod = load_site_module(_CODE)
PaypayCollector = _mod.PaypayCollector


def _make(tmp_path, year=2025):
    return build_collector(tmp_path, _CODE, PaypayCollector, year)


def test_init(tmp_path):
    c = _make(tmp_path)
    assert c.code == _CODE
    assert c.name == "PayPay証券"


def test_is_logged_in_true(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    resp = MagicMock()
    resp.status = 200
    page.goto.return_value = resp
    page.url = "https://www.paypay-sec.co.jp/trade/"
    assert c._is_logged_in(page) is True


def test_is_logged_in_false_on_redirect(tmp_path):
    c = _make(tmp_path)
    page = MagicMock()
    resp = MagicMock()
    resp.status = 200
    page.goto.return_value = resp
    page.url = "https://www.paypay-sec.co.jp/login"
    assert c._is_logged_in(page) is False


def test_collect_calls_login_when_not_logged_in(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_is_logged_in", return_value=False), \
         patch.object(c, "_login") as mock_login, \
         patch.object(c, "_navigate_to_documents"), \
         patch.object(c, "_download_pdf", return_value=None), \
         patch.object(c, "log_result"):
        c.run()

    mock_login.assert_called_once()


def test_collect_skips_login_when_logged_in(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_is_logged_in", return_value=True), \
         patch.object(c, "_login") as mock_login, \
         patch.object(c, "_navigate_to_documents"), \
         patch.object(c, "_download_pdf", return_value=None), \
         patch.object(c, "log_result"):
        c.run()

    mock_login.assert_not_called()


def test_collect_error_when_pdf_not_found(tmp_path):
    c = _make(tmp_path, year=2025)
    page = MagicMock()

    with patch.object(c, "launch_browser", return_value=page), \
         patch.object(c, "close_browser"), \
         patch.object(c, "_is_logged_in", return_value=True), \
         patch.object(c, "_navigate_to_documents"), \
         patch.object(c, "_download_pdf", return_value=None), \
         patch.object(c, "log_result") as mock_log:
        c.run()

    assert mock_log.called
    assert mock_log.call_args[0][0] == "error"
