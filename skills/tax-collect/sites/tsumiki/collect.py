"""tsumiki証券 特定口座年間取引報告書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS        true/false（デフォルト: false）
    DEBUG           true/false（デフォルト: false）
    TSUMIKI_USER    エポスNet ID（未設定時は手動入力）
    TSUMIKI_PASS    パスワード（未設定時は手動入力）

注意:
    ワンタイムパスワード（OTP）はブラウザで直接入力・送信してください。
    スクリプトはブラウザの状態変化を自動検出します。

実測済みページ構造:
    page:  tsumiki-sec.com トップ
    page1: omamori.tsumiki-sec.com SPA（ログイン・操作）
    page2: PDF ビューアポップアップ（特定口座年間取引報告書）

PDF取得方式:
    context.route("**/download_report**") で捕捉。
    page2 の PDF ビューアが自動的に GET /download_report?timestamp を発行する。
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from money_ops.collector.base import BaseCollector

_SITE_JSON = Path(__file__).parent / "site.json"

from money_ops.utils import wait as _wait

class TsumikiCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None, headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _login(self, page) -> object:
        """tsumiki-sec.com → ログインリンク → popup page1（omamori SPA）。

        HAR 確認済み:
          - ログインリンク → popup page1（omamori.tsumiki-sec.com）
          - エポスNet ID + パスワード入力 → ログインするボタン
          - ログイン後: 閉じるボタン（通知等）→ 以降の操作
        """
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        with page.expect_popup() as popup_info:
            page.get_by_role("link", name="ログイン", exact=True).click()
        page1 = popup_info.value
        page1.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.dlog(f"page1 URL: {page1.url}")

        user = os.environ.get("TSUMIKI_USER", "")
        password = os.environ.get("TSUMIKI_PASS", "")

        if user and password:
            page1.get_by_role("textbox", name="エポスNet IDフォーム").fill(user)
            page1.get_by_role("textbox", name="パスワードフォーム").fill(password)
            page1.get_by_role("button", name="ログインする").click()
            _wait(2.0, 3.0)
            print(f"[{self.name}] 自動ログイン完了")
        else:
            print(f"[{self.name}] page1 でログインしてください（エポスNet ID・パスワード）（最大5分）")
            page1.get_by_role("button", name="ログインする").first.wait_for(state="detached", timeout=300_000)
            _wait(2.0, 3.0)

        # 通知等のダイアログを閉じる
        close_btn = page1.get_by_role("button", name="閉じる", exact=True)
        if close_btn.count() > 0:
            close_btn.first.click()
            _wait(0.5, 1.0)

        state_path = self._browser_profile_dir() / "storage_state.json"
        page.context.storage_state(path=str(state_path))
        print(f"[{self.name}] セッション保存: {state_path}")

        return page1

    def _navigate_to_reports(self, page1) -> None:
        """メニュー → 資産の状況 → お取引に関する報告書（電子書面）。

        HAR 確認済み:
          - メニュー画面を開く → #page-main 内「資産の状況を見る」→「お取引に関する報告書」
        """
        print(f"[{self.name}] メニュー → 資産の状況 → 報告書へ移動")
        page1.get_by_role("button", name="メニュー画面を開く").click()
        _wait(1.0, 2.0)

        page1.locator("#page-main").get_by_role("button", name=re.compile("資産の状況を見る")).click()
        page1.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        page1.get_by_role("button", name=re.compile("お取引に関する報告書")).click()
        page1.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.save_html(page1, "after_reports_menu")

    def _handle_otp(self, page1) -> bool:
        """OTP 入力フォームが表示されていれば手動入力を促す。

        HAR 確認済み:
          - send_otp API → メール/SMS → ワンタイムパスワードフォーム表示
          - authenticate_by_otp API で認証
        """
        otp_field = page1.get_by_role("textbox", name="ワンタイムパスワードフォーム")
        if otp_field.count() == 0:
            return True

        print(f"[{self.name}] ワンタイムパスワードをブラウザに入力して「送信してすすむ」を押してください（最大5分）")
        otp_field.wait_for(state="detached", timeout=300_000)
        _wait(2.0, 3.0)
        self.save_html(page1, "after_otp")
        return True

    def _find_report_button(self, page1, target_year: int):
        """特定口座年間取引報告書ボタンを年度で検索。

        HAR 確認済み: ボタン名 = 「特定口座年間取引報告書 作成日 YYYY/MM/DD」
        """
        base = page1.locator("a, button")
        btn = base.filter(has_text=re.compile(r"特定口座年間取引報告書")).filter(
            has_text=re.compile(str(target_year + 1))
        )
        if btn.count() == 0:
            btn = base.filter(has_text=re.compile(r"特定口座年間取引報告書"))
        return btn.first if btn.count() > 0 else None

    def _download_pdf_via_route(self, page1, target_year: int) -> str | None:
        """特定口座年間取引報告書ボタン → page2(PDF viewer) → route 捕捉。

        HAR 確認済み:
          - ボタンクリック → popup page2
          - page2の PDF viewer が GET /download_report?timestamp を発行
          - route で捕捉してバイト保存
        """
        report_btn = self._find_report_button(page1, target_year)
        if report_btn is None:
            self.dlog("特定口座年間取引報告書ボタンが見つかりません")
            return None

        pdf_bytes_holder: list[tuple[str, bytes]] = []
        fallback_name = f"{target_year}_tsumiki_nentori.pdf"

        def _capture_pdf(route, request) -> None:
            response = route.fetch()
            body = response.body()
            if len(body) > 1000:
                cd = response.headers.get("content-disposition", "")
                m = re.search(r'filename[^;=\n]*=([^;\n]*)', cd)
                filename = m.group(1).strip().strip('"\'') if m else fallback_name
                if not filename.endswith(".pdf"):
                    filename = fallback_name
                pdf_bytes_holder.append((filename, body))
            route.fulfill(response=response)

        page1.context.route("**/download_report**", _capture_pdf)
        try:
            with page1.expect_popup() as page2_info:
                report_btn.scroll_into_view_if_needed()
                report_btn.click()
            page2 = page2_info.value
            page2.wait_for_load_state("domcontentloaded")
            _wait(3.0, 5.0)
            page2.close()
        finally:
            page1.context.unroute("**/download_report**", _capture_pdf)

        if not pdf_bytes_holder:
            self.dlog("PDF レスポンスを捕捉できませんでした")
            return None

        self.prepare_directory()
        filename, pdf_bytes = pdf_bytes_holder[0]
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(pdf_bytes)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _collect_core(self, page) -> None:
        page1 = self._login(page)
        year = self.config["target_year"]

        self._navigate_to_reports(page1)

        if not self._handle_otp(page1):
            self.log_result("skip", [], "OTP 入力がキャンセルされました")
            return

        pdf_path = self._download_pdf_via_route(page1, year)
        if pdf_path is None:
            self.log_result("error", [], "PDF 捕捉失敗")
            return

        self._queue_pdf_to_json(pdf_path, [str(Path(pdf_path).name)])
        self.log_result("success", [pdf_path])

def main() -> None:
    parser = argparse.ArgumentParser(description="tsumiki証券 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = TsumikiCollector(year=args.year, headless=args.headless, debug=args.debug)
    collector.run()

if __name__ == "__main__":
    main()
