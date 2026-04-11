"""楽天証券 電子書面ページのセレクタ検証テスト（実際のDOM構造を使用）

fixtures/rakuten_elect_del_top.html を Playwright でロードし、
collect.py が使うセレクタが実際に動作することを確認する。

実機確認済み情報（2026-04-11）:
- 電子書面一覧: https://member.rakuten-sec.co.jp/app/acc_elect_del_top.do
- PDF ポップアップ: https://report.rakuten-sec.co.jp/web/B0020.aspx
- PDF 本体レスポンス: https://report.rakuten-sec.co.jp/web/index.aspx (application/pdf)
"""

from __future__ import annotations

from pathlib import Path

import pytest

_FIXTURE_HTML = Path(__file__).parent / "fixtures" / "rakuten_elect_del_top.html"


@pytest.fixture(scope="module")
def page():
    """Playwright ページを返す fixture"""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    p = browser.new_page()
    yield p
    browser.close()
    pw.stop()


def _load(page):
    page.goto(_FIXTURE_HTML.as_uri())


# ---------------------------------------------------------------------------
# 年度行の特定
# ---------------------------------------------------------------------------

def test_year_row_2025_found(page):
    _load(page)
    rows = page.locator("tr:has(td span:text-is('2025'))")
    assert rows.count() == 1


def test_year_row_2024_found(page):
    _load(page)
    rows = page.locator("tr:has(td span:text-is('2024'))")
    assert rows.count() == 1


def test_year_row_2023_found(page):
    _load(page)
    rows = page.locator("tr:has(td span:text-is('2023'))")
    assert rows.count() == 1


def test_year_row_9999_not_found(page):
    _load(page)
    rows = page.locator("tr:has(td span:text-is('9999'))")
    assert rows.count() == 0


# ---------------------------------------------------------------------------
# 2025年行の XML保存・PDF表示ボタン
# ---------------------------------------------------------------------------

def test_2025_xml_button_found(page):
    _load(page)
    year_row = page.locator("tr:has(td span:text-is('2025'))")
    xml_btn = year_row.get_by_role("button", name="XML保存")
    assert xml_btn.count() == 1


def test_2025_pdf_link_found(page):
    _load(page)
    year_row = page.locator("tr:has(td span:text-is('2025'))")
    pdf_link = year_row.get_by_role("link", name="PDF表示")
    assert pdf_link.count() == 1


# ---------------------------------------------------------------------------
# 年度をまたいで誤クリックしないことの確認
# ---------------------------------------------------------------------------

def test_2025_xml_button_not_2024(page):
    """2025年行のXML保存ボタンが2024年のものでないことを確認"""
    _load(page)
    year_row = page.locator("tr:has(td span:text-is('2025'))")
    xml_btn = year_row.get_by_role("button", name="XML保存")
    onclick = xml_btn.get_attribute("onclick")
    assert "'2025'" in onclick
    assert "'2024'" not in onclick


def test_2024_xml_button_not_2025(page):
    _load(page)
    year_row = page.locator("tr:has(td span:text-is('2024'))")
    xml_btn = year_row.get_by_role("button", name="XML保存")
    onclick = xml_btn.get_attribute("onclick")
    assert "'2024'" in onclick
    assert "'2025'" not in onclick


def test_first_xml_button_is_not_reliable(page):
    """ページ全体の最初のXML保存が必ずしも対象年度とは限らないことを確認"""
    _load(page)
    all_xml = page.get_by_role("button", name="XML保存")
    assert all_xml.count() == 3  # 2025, 2024, 2023 の3行ある
    # .first は 2025年だが、年度が変われば壊れる → 年度特定が必要
