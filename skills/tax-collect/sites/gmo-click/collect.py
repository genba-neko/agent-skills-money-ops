"""GMOクリック証券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）

注意:
    ログインは人間が手動で行う。
    スクリプト起動後、ブラウザでトップ画面まで到達してから Enter を押すこと。
    電子書類閲覧へのアクセス時にアプリ2FA が発生する。
    2FAコードを入力したら Enter を押すこと（認証ボタンはスクリプトが押す）。
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

class GMOClickCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None, headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _wait_for_login(self, page) -> None:
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        url = page.url
        if isinstance(url, str) and "mypage/top" in url:
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            self._session = page
            self.dlog(f"URL: {page.url}")
            self.save_html(page, "after_login_skip")
            return
        print(f"[{self.name}] ブラウザでログインしてください")
        self.prompt("ログイン完了後 Enter を押してください: ")
        _wait()
        self._session = page
        self.dlog(f"URL: {page.url}")
        self.save_html(page, "after_login")
        # セッション状態（cookie含む）を保存
        page.context.storage_state(path=str(self._browser_profile_dir() / "storage_state.json"))
        print(f"[{self.name}] セッション状態を保存しました")

    def _navigate_to_report_popup(self) -> object:
        """電子書類閲覧ポップアップを開いて返す"""
        session = self._session
        # ログイン直後の通知を閉じる（表示される場合のみ）
        close_btn = session.get_by_role("link", name="閉じる")
        if close_btn.count() > 0:
            close_btn.click()
            _wait()
        print(f"[{self.name}] 精算表 → 電子書類閲覧 → 書類閲覧リンク へ移動")
        session.locator("a").filter(has_text="精算表").first.click()
        _wait()
        session.get_by_role("link", name="電子書類閲覧").click()
        _wait()
        session.locator("#stockReportLink").click()
        _wait(2.0, 3.0)
        # 2FAモーダルが表示された場合のみ処理（セッション状態によって有無が変わる）
        if session.locator("#appTwoStepVerificationCode").is_visible():
            print(f"[{self.name}] アプリ2FAコードを入力してください（認証ボタンはスクリプトが押します）")
            self.prompt("コード入力後 Enter を押してください: ")
            with session.expect_popup() as popup_info:
                session.locator("#btnConfirm").click()
            popup = popup_info.value
        else:
            # 2FAなし: #stockReportLink クリックでポップアップが開く（遅延考慮でリトライ）
            popup = None
            for _ in range(6):
                new_pages = [p for p in session.context.pages if p is not session]
                if new_pages:
                    popup = new_pages[-1]
                    break
                _wait(0.5, 1.0)
            if popup is None:
                raise RuntimeError(f"[{self.name}] ポップアップが開きませんでした")
        popup.wait_for_load_state("domcontentloaded")
        # e-shishobako Angular SPA: SSO後のルーティング完了を待つ（SBIと同方式）
        popup.wait_for_url("**/dp_apl/usr/**", timeout=30000)
        popup.wait_for_selector("input, button", timeout=30000)
        _wait(2.0, 3.0)
        self.dlog(f"popup URL: {popup.url}")
        self.save_html(popup, "report_popup")
        return popup

    def _find_report_row_button(self, popup, target_year: int):
        """target_year に対応する年月ボタンを返す（なければ None）
        get_by_role("button") で role="button" の div 要素も対象にする（SBIと同方式）"""
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
        _wait(2.0, 3.0)

        row_btn = self._find_report_row_button(popup, year)
        if row_btn is None:
            print(f"[{self.name}] {year}年度の報告書が見つかりません")
            return downloaded
        print(f"[{self.name}] 報告書行をクリック（詳細を開く）")
        row_btn.scroll_into_view_if_needed()
        row_btn.click()
        # PDF ダウンロードボタンが visible になるまで待機（SBIと同方式）
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

        # PDF（e-shishobako DPAW010501020 ルート捕捉）
        pdf_path = capture_dpaw_pdf(
            popup, self.output_dir, f"{year}_nentori.pdf", label=self.name
        )
        if pdf_path:
            downloaded.append(pdf_path)
            _wait()

        return downloaded

    def _collect_core(self, page) -> None:
        self._wait_for_login(page)
        popup = self._navigate_to_report_popup()

        downloaded = self._download_files(popup)
        if not downloaded:
            self.log_result("skip", [], "ダウンロード対象ファイルが見つかりませんでした")
            return

        self._convert_xml_to_json(downloaded)
        self.log_result("success", downloaded)

def main() -> None:
    parser = argparse.ArgumentParser(description="GMOクリック証券 年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = GMOClickCollector(year=args.year, headless=args.headless, debug=args.debug)
    collector.run()

if __name__ == "__main__":
    main()
