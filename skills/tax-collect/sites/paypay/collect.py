"""PayPay証券 特定口座年間取引報告書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS        true/false（デフォルト: false）
    DEBUG           true/false（デフォルト: false）
    PAYPAY_USER     会員ID（未設定時は手動入力）
    PAYPAY_PASS     パスワード（未設定時は手動入力）

注意:
    SMS 認証コード（6桁）は必ず手動入力が必要。

実測済みページ構造（HAR確認済み）:
    page: paypay-sec.co.jp/ → /account/login/ → /login/
    → POST /login.json → /noauth/emailauth
    → POST /noauth/emailauth/verify_otp_code → /trade/
    → /trade/documents/ → tr.pdf_download 行 → HREF取得
    → GET /trade/documents/download/{id} → 303 → S3 PDF

PDF取得方式:
    page.request.get(HREF) で 303 リダイレクトを追跡し S3 PDF を直接取得。
    route 捕捉不要。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.collector.base import BaseCollector
from money_ops.converter.pdf_to_json import convert_pdf_to_json

_SITE_JSON = Path(__file__).parent / "site.json"
_TOP_URL = "https://www.paypay-sec.co.jp/"
_TRADE_URL = "https://www.paypay-sec.co.jp/trade/"


from money_ops.utils import wait as _wait


class PaypayCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path)
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/paypay/{year}/raw/"
            self.output_dir = Path(self.config["output_dir"])

    def _is_logged_in(self, page) -> bool:
        """セッション有効チェック: /trade/ にアクセスして確認。
        ログイン済み → 200 かつ /trade/ に留まる。
        未ログイン → ログインページへリダイレクト。
        """
        resp = page.goto(_TRADE_URL)
        page.wait_for_load_state("domcontentloaded")
        _wait(1.0, 2.0)
        return resp is not None and resp.ok and "/trade/" in page.url

    def _login(self, page) -> None:
        """paypay-sec.co.jp → ログイン → PC取引画面 → 会員ID+パスワード → SMS認証。

        HAR 確認済み:
          - ログインリンク → /account/login/ → PC取引画面へログイン → /login/
          - 会員ID + パスワード → POST /login.json
          - SMS 6桁（#code1-#code6） → #btn_sms_success クリック
            → POST /noauth/emailauth/verify_otp_code (otp_prefix は hidden field 自動送信)
          - 認証後: /trade/ へリダイレクト
        """
        page.goto(_TOP_URL)
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        page.get_by_role("link", name="ログイン").first.click()
        page.wait_for_load_state("domcontentloaded")
        _wait(1.0, 2.0)

        page.get_by_role("link", name="PC取引画面へログイン").first.click()
        page.wait_for_load_state("domcontentloaded")
        _wait(1.0, 2.0)
        self.dlog(f"login page URL: {page.url}")

        user = os.environ.get("PAYPAY_USER", "")
        password = os.environ.get("PAYPAY_PASS", "")

        if user and password:
            page.get_by_role("textbox", name="会員ID").fill(user)
            page.get_by_role("textbox", name="パスワード").fill(password)
            page.get_by_role("link", name="ログイン").first.click()
            _wait(2.0, 3.0)
            self.save_html(page, "after_credential_submit")
        else:
            print(f"[{self.name}] 会員ID・パスワードをブラウザで入力してログインボタンを押してください")
            input("ログインボタン押下後 Enter: ")

        # emailauth か /trade/ のどちらかに遷移するまで待つ
        page.wait_for_url(
            lambda url: "emailauth" in url or "/trade/" in url,
            timeout=60000,
        )
        _wait(1.0, 2.0)
        self.dlog(f"after login URL: {page.url}")

        # SMS 認証
        if "emailauth" in page.url:
            print(f"[{self.name}] SMS 認証コード（6桁）を入力してください")
            code = input("コード: ").strip()
            if len(code) != 6 or not code.isdigit():
                raise ValueError(f"SMS コードは6桁の数字です: {code!r}")
            for i, digit in enumerate(code, 1):
                page.locator(f"#code{i}").fill(digit)
            page.locator("#btn_sms_success").click()
            page.wait_for_url("**/trade/**", timeout=120000)
            _wait(2.0, 3.0)

        self.dlog(f"trade URL: {page.url}")
        state_path = self._browser_profile_dir() / "storage_state.json"
        page.context.storage_state(path=str(state_path))
        print(f"[{self.name}] セッション保存: {state_path}")

    def _navigate_to_documents(self, page) -> None:
        """メニュー → 電子交付書類 (/trade/documents/)。

        HAR 確認済み:
          - メニューリンク → 電子交付書類リンク → /trade/documents/
        """
        print(f"[{self.name}] メニュー → 電子交付書類へ移動")
        page.get_by_role("link", name="メニュー").click()
        _wait(1.0, 2.0)
        page.get_by_role("link", name="電子交付書類").click()
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.save_html(page, "documents_list")

    def _download_pdf(self, page, target_year: int) -> str | None:
        """特定口座年間取引報告書の行を特定し、HREF の GET で PDF を取得。

        HAR 確認済み:
          - tr.pdf_download[HREF='/trade/documents/download/{id}'] で行を特定
          - BASE_D='YYYY.MM.DD' (2025年報告書は 2026 年発行)
          - GET /trade/documents/download/{id} → 303 redirect → S3 application/pdf
          - page.request.get() が 303 を自動追跡し PDF bytes を返す
        """
        issue_year = str(target_year + 1)

        rows = page.locator("tr.pdf_download").filter(has_text="特定口座年間取引報告書")
        if rows.count() == 0:
            print(f"[{self.name}] 特定口座年間取引報告書 行が見つかりません")
            return None

        target_row = rows.filter(has_text=issue_year)
        if target_row.count() == 0:
            print(f"[{self.name}] {issue_year}年発行の特定口座年間取引報告書が見つかりません")
            return None

        # HREF 属性取得（大文字・小文字両対応）
        href = target_row.first.evaluate(
            "el => el.getAttribute('HREF') || el.getAttribute('href')"
        )
        if not href:
            print(f"[{self.name}] HREF 属性なし")
            return None

        dl_url = urljoin(_TOP_URL, href)
        self.dlog(f"PDF download URL: {dl_url}")

        response = page.request.get(dl_url)
        pdf_bytes = response.body()

        if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
            print(f"[{self.name}] PDF でないレスポンス: {len(pdf_bytes)} bytes, CT={response.headers.get('content-type','?')}")
            return None

        self.prepare_directory()
        filename = f"{target_year}_paypay_nentori.pdf"
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(pdf_bytes)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _collect_core(self, page) -> None:
        year = self.config.get("target_year")
        if year is None:
            raise ValueError("target_year が設定されていません")

        if not self._is_logged_in(page):
            self._login(page)

        self._navigate_to_documents(page)

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
    parser = argparse.ArgumentParser(description="PayPay証券 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    args = parser.parse_args()
    collector = PaypayCollector(year=args.year)
    collector.run()


if __name__ == "__main__":
    main()
