"""SBI証券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）

注意:
    ログイン・2FA・ポップアップ処理は人間が手動で行う。
    スクリプト起動後、ブラウザでトップ画面まで到達してから Enter を押すこと。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from money_ops.collector.base import BaseCollector

_SITE_JSON = Path(__file__).parent / "site.json"

from money_ops.collector.eshishobako import capture_dpaw_pdf
from money_ops.utils import wait as _wait

def _year_month_patterns(target_year: int) -> list[str]:
    """発行年月の候補: 対象年12月 or 翌年1月"""
    return [f"{target_year}/12", f"{target_year + 1}/01"]

class SBICollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None, headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _wait_for_login(self, page) -> None:
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        if page.locator('input[name="username"]').count() == 0:
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            self.dlog(f"URL: {page.url}")
            self.save_html(page, "after_login_skip")
            return
        print(f"[{self.name}] ブラウザでログイン・OTP等をすべて完了してください")
        self.prompt("トップ画面で操作可能になったら Enter を押してください: ")
        _wait()
        self.dlog(f"URL: {page.url}")
        self.save_html(page, "after_login")
        # ログイン直後にセッション状態（Cookie・デバイス登録情報）を明示的に保存
        page.context.storage_state(path=str(self._browser_profile_dir() / "storage_state.json"))
        print(f"[{self.name}] セッション状態を保存しました")

    def _navigate_to_report_popup(self, page):
        """電子交付書面ポップアップを開いて返す"""
        print(f"[{self.name}] 口座管理 → 取引報告書等(電子交付) → 報告書閲覧 へ移動")
        page.get_by_role("link", name="口座管理").first.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        _wait()
        page.get_by_role("link", name="取引報告書等(電子交付)").first.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        _wait()
        with page.expect_popup() as popup_info:
            page.get_by_role("button", name="報告書閲覧").first.click()
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded")
        # Angular SPA の初期化完了を待つ（e-shishobako.ne.jp）
        # SSO リダイレクト後に Angular がコンポーネントを描画するまで待機
        popup.wait_for_url("**/dp_apl/usr/**", timeout=30000)
        popup.wait_for_selector("input, button", timeout=30000)
        _wait(2.0, 3.0)
        self.dlog(f"popup URL: {popup.url}")
        self.save_html(popup, "report_popup")
        return popup

    def _find_report_row_button(self, popup, target_year: int):
        """target_year に対応する年月ボタンを返す（なければ None）"""
        for ym in _year_month_patterns(target_year):
            btn = popup.get_by_role("button").filter(has_text=ym)
            if btn.count() > 0:
                return btn.first
        return None

    def _download_files(self, popup) -> list[str]:
        self.prepare_directory()
        year = self.config["target_year"]
        downloaded: list[str] = []

        # キーワード絞り込み（Angular SPA なのでクライアントサイドフィルタ）
        search_box = popup.get_by_role("textbox", name="キーワードで件名検索")
        search_box.fill("特定口座年間取引報告書")
        search_box.press("Enter")
        _wait(2.0, 3.0)  # Angular のフィルタ反映を待つ（networkidle 無効）

        row_btn = self._find_report_row_button(popup, year)
        if row_btn is None:
            print(f"[{self.name}] {year}年度の報告書が見つかりません")
            return downloaded
        print(f"[{self.name}] 報告書行をクリック（詳細を開く）")
        row_btn.scroll_into_view_if_needed()
        row_btn.click()
        # PDF ダウンロードボタン（button または a）が visible になるまで待機
        popup.locator("button, a").filter(has_text="PDFファイル").first.wait_for(
            state="visible", timeout=15000
        )
        _wait()

        # XML（button または a 要素）
        xml_btn = popup.locator("button, a").filter(has_text="xmlデータ")
        if xml_btn.count() == 0:
            xml_btn = popup.locator("button, a").filter(has_text="XMLデータ")
        if xml_btn.count() > 0:
            with popup.expect_download() as dl_info:
                xml_btn.click()
            dl = dl_info.value
            xml_path = self.output_dir / dl.suggested_filename
            dl.save_as(str(xml_path))
            downloaded.append(str(xml_path))
            print(f"[{self.name}] XML 保存: {xml_path}")
            _wait()
        else:
            print(f"[{self.name}] XML ボタンが見つかりません")

        # PDF
        pdf_path = capture_dpaw_pdf(
            popup, self.output_dir, f"{year}_nentori.pdf", label=self.name
        )
        if pdf_path:
            downloaded.append(pdf_path)
            _wait()

        return downloaded

    def _collect_core(self, page) -> None:
        self._wait_for_login(page)
        popup = self._navigate_to_report_popup(page)

        downloaded = self._download_files(popup)
        if not downloaded:
            self.log_result("skip", [], "ダウンロード対象ファイルが見つかりませんでした")
            return

        self._convert_xml_to_json(downloaded)
        self.log_result("success", downloaded)

def main() -> None:
    parser = argparse.ArgumentParser(description="SBI証券 年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = SBICollector(year=args.year, headless=args.headless, debug=args.debug)
    collector.run()

if __name__ == "__main__":
    main()
