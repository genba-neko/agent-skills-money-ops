"""さわかみ投信 特定口座年間取引報告書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS        true/false（デフォルト: false）
    DEBUG           true/false（デフォルト: false）
    SAWAKAMI_USER   ログインID（未設定時は手動入力）
    SAWAKAMI_PASS   ログインパスワード（未設定時は手動入力）

注意:
    メール認証コード（6桁）は必ず手動入力が必要。

実測済みページ構造（HAR確認済み）:
    GET  /Account/Login
    POST /Account/Login → 302
    GET  /account/twofactorauth?provider=Email&ReturnUrl=%2F&RememberMe=False
    POST /account/twofactorauth?returnUrl=/ → 302 → /

PDF取得方式:
    GET /e-delivery?sf=Inbox&fo=Unopened&fo=Opened&dd_f={issue_year}/01/01&rep_ty=03
    .contents-item 内の「特定口座年間取引報告書」をテキストフィルター
    a.x-shadowButton.x-m-download クリック
    XHR POST /e-delivery?handler=Download → blob
    Utils.localDownload() → <a download> → page.expect_download() で捕捉

e-delivery フィルター:
    rep_ty=01 取引報告書（デフォルト選択）
    rep_ty=02 取引残高報告書（デフォルト選択）
    rep_ty=03 特定口座年間取引報告書（UI では disabled）
    rep_ty=31 運用報告書（デフォルト選択）
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from money_ops.collector.base import BaseCollector
from money_ops.converter.pdf_to_json import convert_pdf_to_json

_SITE_JSON = Path(__file__).parent / "site.json"
_LOGIN_URL = "https://fv.sawakami.co.jp/Account/Login"
_EDELIVERY_URL = "https://fv.sawakami.co.jp/e-delivery"

from money_ops.utils import wait as _wait

class SawakamiCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path, year)

    def _is_logged_in(self, page) -> bool:
        """セッション有効チェック: /e-delivery にアクセスしてログイン済みか確認。

        サーバーは未認証時でも /e-delivery?sf=Inbox&... へリダイレクトし、
        その URL でログインフォームを表示する（URL だけでは判別不可）。
        input[name="Input.LoginId"] の存在でログインページかを判定する。
        """
        resp = page.goto(_EDELIVERY_URL)
        page.wait_for_load_state("domcontentloaded")
        _wait(1.0, 2.0)
        if resp is None or not resp.ok or "e-delivery" not in page.url:
            return False
        return page.locator("input[name='Input.LoginId']").count() == 0

    def _login(self, page) -> None:
        """ログイン → メール2FA → セッション保存。

        HAR 確認済み:
          - GET  /Account/Login
          - POST /Account/Login → 302
          - GET  /account/twofactorauth?provider=Email&ReturnUrl=%2F&RememberMe=False
          - POST /account/twofactorauth?returnUrl=/ → 302 → /
        """
        page.goto(_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        user = os.environ.get("SAWAKAMI_USER", "")
        password = os.environ.get("SAWAKAMI_PASS", "")

        if user and password:
            page.get_by_role("textbox", name="ログインID").fill(user)
            page.get_by_role("textbox", name="ログインパスワード").fill(password)
            page.get_by_role("button", name="ログイン").click()
            _wait(2.0, 3.0)
            self.save_html(page, "after_credential_submit")
        else:
            print(f"[{self.name}] ログインID・パスワードをブラウザで入力してログインボタンを押してください")
            input("ログインボタン押下後 Enter: ")

        # twofactorauth か home のどちらかを待つ
        page.wait_for_url(
            lambda url: "twofactorauth" in url or url.rstrip("/") == "https://fv.sawakami.co.jp",
            timeout=60000,
        )
        _wait(1.0, 2.0)
        self.dlog(f"after login URL: {page.url}")

        if "Account/Login" in page.url:
            raise RuntimeError("ログイン失敗: 認証情報を確認してください")

        # メール 2FA
        if "twofactorauth" in page.url:
            print(f"[{self.name}] メール認証コードを入力してください")
            code = input("認証コード: ").strip()
            page.get_by_role("spinbutton", name="認証コード").fill(code)
            page.get_by_role("button", name="認証する").click()
            page.wait_for_url(
                lambda url: "twofactorauth" not in url,
                timeout=120000,
            )
            _wait(2.0, 3.0)

        self.dlog(f"logged in URL: {page.url}")
        state_path = self._browser_profile_dir() / "storage_state.json"
        state = page.context.storage_state()
        if state.get("cookies"):
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"[{self.name}] セッション保存: {state_path}")

    def _download_pdf(self, page, target_year: int) -> str | None:
        """e-delivery から特定口座年間取引報告書を取得。

        HAR 確認済み:
          - GET /e-delivery?sf=Inbox&fo=Unopened&fo=Opened&dd_f={issue_year}/01/01&rep_ty=03
          - .contents-item 内の見出しテキストで「特定口座年間取引報告書」を特定
          - a.x-shadowButton.x-m-download クリック
          - XHR POST /e-delivery?handler=Download → blob → Utils.localDownload() →
            <a download> click → page.expect_download() で捕捉
          - rep_ty=03 は UI checkbox が disabled だが URL 直指定でフィルタ可能
        """
        issue_year = target_year + 1
        url = (
            f"{_EDELIVERY_URL}?sf=Inbox&fo=Unopened&fo=Opened"
            f"&dd_f={issue_year}/01/01&rep_ty=03"
        )
        self.dlog(f"e-delivery URL: {url}")
        page.goto(url)
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.save_html(page, "edelivery_list")

        # 特定口座年間取引報告書の .contents-item を特定（発行年で絞り込み）
        items = (
            page.locator(".contents-item")
            .filter(has_text="特定口座年間取引報告書")
            .filter(has_text=str(issue_year))
        )
        if items.count() == 0:
            # フォールバック: rep_ty=03 未対応の場合は rep_ty 指定なしで全件取得
            self.dlog("rep_ty=03 で見つからず → rep_ty 指定なしでフォールバック")
            fallback_url = (
                f"{_EDELIVERY_URL}?sf=Inbox&fo=Unopened&fo=Opened"
                f"&dd_f={issue_year}/01/01"
            )
            page.goto(fallback_url)
            page.wait_for_load_state("domcontentloaded")
            _wait(2.0, 3.0)
            self.save_html(page, "edelivery_list_fallback")
            items = (
                page.locator(".contents-item")
                .filter(has_text="特定口座年間取引報告書")
                .filter(has_text=str(issue_year))
            )

        if items.count() == 0:
            print(f"[{self.name}] 特定口座年間取引報告書が見つかりません（{issue_year}年発行分）")
            return None

        target_item = items.first
        dl_button = target_item.locator("a.x-shadowButton.x-m-download")
        if dl_button.count() == 0:
            print(f"[{self.name}] ダウンロードボタンが見つかりません")
            return None

        self.prepare_directory()
        filename = f"{target_year}_sawakami_nentori.pdf"

        with page.expect_download(timeout=60000) as dl_info:
            dl_button.click()
        download = dl_info.value

        pdf_path = self.output_dir / filename
        download.save_as(str(pdf_path))

        failure = download.failure()
        if failure:
            print(f"[{self.name}] ダウンロード失敗: {failure}")
            pdf_path.unlink(missing_ok=True)
            return None

        # PDF 検証
        pdf_bytes = pdf_path.read_bytes()
        if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
            print(f"[{self.name}] PDF でないファイル: {len(pdf_bytes)} bytes")
            pdf_path.unlink(missing_ok=True)
            return None

        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _collect_core(self, page) -> None:
        year = self.config.get("target_year")
        if year is None:
            raise ValueError("target_year が設定されていません")

        if not self._is_logged_in(page):
            self._login(page)

        pdf_path = self._download_pdf(page, year)
        if pdf_path is None:
            self.log_result("error", [], "PDF 取得失敗")
            return

        try:
            data = convert_pdf_to_json(
                pdf_path=pdf_path,
                company=self.name,
                code=self.code,
                year=year,
                raw_files=[str(Path(pdf_path).name)],
            )
            self._write_report_json(data)
        except Exception as e:
            print(f"[{self.name}] JSON 変換スキップ: {e}")

        self.log_result("success", [pdf_path])

def main() -> None:
    parser = argparse.ArgumentParser(description="さわかみ投信 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    args = parser.parse_args()
    collector = SawakamiCollector(year=args.year)
    collector.run()

if __name__ == "__main__":
    main()
