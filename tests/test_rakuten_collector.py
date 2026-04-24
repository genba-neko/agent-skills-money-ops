"""楽天証券収集スクリプトのユニットテスト（Playwright モック）"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

_SITE_JSON = _PROJECT_ROOT / "skills" / "tax-collect" / "sites" / "rakuten" / "site.json"

import importlib.util

_COLLECT_PY = _PROJECT_ROOT / "skills" / "tax-collect" / "sites" / "rakuten" / "collect.py"
_spec = importlib.util.spec_from_file_location("rakuten_collect", _COLLECT_PY)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RakutenCollector = _mod.RakutenCollector


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _make_collector(tmp_path: Path, year: int = 2025) -> RakutenCollector:
    config = json.loads(_SITE_JSON.read_text(encoding="utf-8"))
    config["output_dir"] = str(tmp_path / "raw")
    config["target_year"] = year
    tmp_site = tmp_path / "site.json"
    tmp_site.write_text(json.dumps(config), encoding="utf-8")
    # year=None で渡して config の値を使わせる（output_dir 上書きを防ぐ）
    return RakutenCollector(site_json_path=tmp_site)


# ---------------------------------------------------------------------------
# 初期化テスト
# ---------------------------------------------------------------------------

def test_init_default_year(tmp_path):
    collector = _make_collector(tmp_path)
    assert collector.config["target_year"] == 2025
    assert collector.code == "rakuten"
    assert collector.name == "楽天証券"


def test_init_override_year(tmp_path):
    collector = _make_collector(tmp_path, year=2024)
    assert collector.config["target_year"] == 2024
    assert collector.output_dir == tmp_path / "raw"


# ---------------------------------------------------------------------------
# 手動ログイン待機テスト
# ---------------------------------------------------------------------------

def test_wait_for_login(tmp_path):
    collector = _make_collector(tmp_path)
    page = MagicMock()

    with patch.object(_mod, "_wait"), patch("builtins.input", return_value=""):
        collector._wait_for_login(page)

    page.goto.assert_called_once_with(collector.config["login_url"])


# ---------------------------------------------------------------------------
# ナビゲーションテスト
# ---------------------------------------------------------------------------

def test_navigate_to_report_list(tmp_path):
    collector = _make_collector(tmp_path, year=2025)
    page = MagicMock()

    calls = []

    def get_by_role_side(role, **kwargs):
        calls.append((role, kwargs.get("name", "")))
        return MagicMock()

    page.get_by_role.side_effect = get_by_role_side

    with patch.object(_mod, "_wait"):
        collector._navigate_to_report_list(page)

    names = [name for _, name in calls]
    assert "マイメニュー 口座管理・入出金など" in names
    assert "確定申告サポート" in names
    assert "2025年" in names
    assert "取引報告書等(電子書面)" in names


# ---------------------------------------------------------------------------
# ダウンロードテスト
# ---------------------------------------------------------------------------

def _make_download_mock(saved_paths: list, content: bytes = b"dummy"):
    dl = MagicMock()

    def save_as(path):
        saved_paths.append(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(content)

    dl.value.save_as = save_as
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=dl)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_download_files_xml_and_pdf(tmp_path):
    collector = _make_collector(tmp_path, year=2025)
    saved: list[str] = []

    page = MagicMock()
    context = MagicMock()
    page.context = context

    # 年度行あり
    year_row = MagicMock()
    year_row.count.return_value = 1

    xml_button = MagicMock()
    xml_button.count.return_value = 1
    pdf_link = MagicMock()
    pdf_link.count.return_value = 1

    def get_by_role_side(role, **kwargs):
        name = kwargs.get("name", "")
        if "XML" in name:
            return xml_button
        return pdf_link

    year_row.get_by_role.side_effect = get_by_role_side
    page.locator.return_value = year_row

    # XML ダウンロード: suggested_filename を返す
    dl_mock = MagicMock()
    dl_mock.suggested_filename = "1234-Z00-00000000001.xml"

    def save_as_side(path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"<xml/>")
        saved.append(path)

    dl_mock.save_as.side_effect = save_as_side
    dl_cm = MagicMock()
    dl_cm.__enter__ = MagicMock(return_value=MagicMock(value=dl_mock))
    dl_cm.__exit__ = MagicMock(return_value=False)
    page.expect_download.return_value = dl_cm

    # PDF ポップアップ
    popup = MagicMock()
    popup_cm = MagicMock()
    popup_cm.__enter__ = MagicMock(return_value=MagicMock(value=popup))
    popup_cm.__exit__ = MagicMock(return_value=False)
    page.expect_popup.return_value = popup_cm

    # route ハンドラが呼ばれたとき PDF を注入
    def context_route_side(pattern, handler):
        # ハンドラを即時呼び出してPDFバイトを注入
        route = MagicMock()
        response = MagicMock()
        response.headers = {"content-type": "application/pdf"}
        response.status = 200
        response.body.return_value = b"%PDF-dummy"
        route.fetch.return_value = response
        request = MagicMock()
        request.url = "https://report.rakuten-sec.co.jp/web/index.aspx"
        handler(route, request)

    context.route.side_effect = context_route_side

    with patch.object(_mod, "_wait"):
        result = collector._download_files(page)

    # XML は保存される
    assert any(".xml" in p for p in saved)
    # PDF は保存される
    assert any(".pdf" in p for p in result)


def test_download_files_year_row_not_found(tmp_path):
    collector = _make_collector(tmp_path, year=2025)
    page = MagicMock()
    page.locator.return_value.count.return_value = 0

    with patch.object(_mod, "_wait"):
        result = collector._download_files(page)

    assert result == []


def test_download_files_no_xml_button(tmp_path):
    collector = _make_collector(tmp_path, year=2025)
    page = MagicMock()

    year_row = MagicMock()
    year_row.count.return_value = 1
    page.locator.return_value = year_row

    xml_button = MagicMock()
    xml_button.count.return_value = 0
    pdf_link = MagicMock()
    pdf_link.count.return_value = 0

    def get_by_role_side(role, **kwargs):
        name = kwargs.get("name", "")
        if "XML" in name:
            return xml_button
        return pdf_link

    year_row.get_by_role.side_effect = get_by_role_side

    with patch.object(_mod, "_wait"):
        result = collector._download_files(page)

    assert result == []


# ---------------------------------------------------------------------------
# JSON 変換テスト
# ---------------------------------------------------------------------------

def test_convert_to_json_skips_without_xml(tmp_path, capsys):
    collector = _make_collector(tmp_path)
    collector._convert_xml_to_json(["data/foo.pdf"])
    captured = capsys.readouterr()
    assert "スキップ" in captured.out


def test_convert_to_json_with_xml(tmp_path):
    fixture_xml = _PROJECT_ROOT / "tests" / "fixtures" / "teg204_sample.xml"
    if not fixture_xml.exists():
        pytest.skip("teg204_sample.xml が存在しません")

    collector = _make_collector(tmp_path)
    collector.output_dir.mkdir(parents=True, exist_ok=True)
    collector._convert_xml_to_json([str(fixture_xml)])

    json_path = collector.output_dir.parent / "nenkantorihikihokokusho.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["code"] == "rakuten"
    assert data["source"] == "xml"


# ---------------------------------------------------------------------------
# collect() スキップフロー
# ---------------------------------------------------------------------------

def test_collect_skip_when_year_row_not_found(tmp_path):
    collector = _make_collector(tmp_path, year=2025)
    page = MagicMock()

    def locator_side_effect(selector):
        m = MagicMock()
        m.count.return_value = 0
        m.filter.return_value.count.return_value = 0
        return m

    page.locator.side_effect = locator_side_effect

    with patch.object(collector, "launch_browser", return_value=page), \
         patch.object(collector, "close_browser"), \
         patch.object(collector, "_wait_for_login"), \
         patch.object(collector, "_save_session_state"), \
         patch.object(collector, "_navigate_to_report_list"), \
         patch.object(collector, "log_result") as mock_log, \
         patch.object(_mod, "_wait"):
        collector.run()

    mock_log.assert_called_once_with("skip", [], f"{collector.config['target_year']}年の取引報告書が存在しません")
