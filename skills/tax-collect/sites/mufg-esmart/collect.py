"""MUFG eスマート証券 特定口座年間取引報告書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS            true/false（デフォルト: false）
    DEBUG               true/false（デフォルト: false）
    MUFGESMART_USER     口座番号（未設定時は手動入力）
    MUFGESMART_PASS     パスワード（未設定時は手動入力）

注意:
    ログイン後のワンタイム認証コード（メール）は必ず手動入力が必要。

実測済みページ構造（HAR確認済み）:
    page:  kabu.com（トップ）
    page1: auth.kabu.co.jp（Auth0）→ s20.si1.kabu.co.jp（取引画面）
    page2: e-私書箱連携 popup（初回のみ・条件付き）

Auth0 フロー:
    GET /u/login/identifier → POST（口座番号）
    → GET /u/login/password → POST（パスワード）
    → GET /u/mfa-email-challenge → POST（OTPコード）
    → mauth-sso.kabu.co.jp/masession/auth/callback/pc/auth0
    → s20.si1.kabu.co.jp/members/

PDF取得方式:
    page1.expect_download() で捕捉。
    報告書等 → PDFReport/Search → 期間・報告書名フィルター → 検索 → PDF DL。
    GET /ap/PC/PDFReport/PDFReport/Print?sakuseidate=...&ListId=...&typeFlag=false
    Content-Disposition: attachment; filename=Report{ListId}_{timestamp}.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from money_ops.collector.base import BaseCollector
from money_ops.converter.pdf_to_json import convert_pdf_to_json

_SITE_JSON = Path(__file__).parent / "site.json"

from money_ops.utils import wait as _wait

class MufgEsmartCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None, headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _save_session(self, page) -> None:
        """cookie が存在する場合のみ storage_state.json を保存（空書き込みで既存 cookie 喪失を防ぐ）。"""
        state = page.context.storage_state()
        if not state.get("cookies"):
            self.dlog("storage_state が空のため保存スキップ")
            return
        state_path = self._browser_profile_dir() / "storage_state.json"
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"[{self.name}] セッション保存: {state_path} ({len(state['cookies'])} cookies)")

    def _open_trade_page(self, page) -> object:
        """kabu.com → ログイン popup → 取引ページ（page1）。

        HAR 確認済み:
          - #pc-header ログインリンク → popup page1（auth.kabu.co.jp Auth0）
          - Auth0: 口座番号 → 次へ → パスワード → ログイン → メールOTP → 続ける
          - 認証後: mauth-sso callback → s20.si1.kabu.co.jp/members/
          - セッション有効時: Auth0 がフォームをスキップして直接 si1.kabu.co.jp へ
        """
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        with page.expect_popup() as page1_info:
            page.locator("#pc-header").get_by_role("link", name="ログイン").click()
        page1 = page1_info.value
        page1.wait_for_load_state("domcontentloaded")

        # Auth0 の identifier ページ・mauth-sso コールバック・si1.kabu.co.jp のいずれかを待つ
        try:
            page1.wait_for_url(
                lambda url: "identifier" in url or "mauth-sso" in url or "si1.kabu.co.jp" in url,
                timeout=15000,
            )
            # mauth-sso 経由の場合はさらに si1.kabu.co.jp まで待つ
            if "mauth-sso" in page1.url:
                page1.wait_for_url(lambda u: "si1.kabu.co.jp" in u, timeout=15000)
        except Exception:
            pass
        _wait(1.0, 2.0)
        self.dlog(f"page1 URL: {page1.url}")

        # セッション有効: Auth0 ログインフォームをスキップして si1.kabu.co.jp へ直接遷移
        if "si1.kabu.co.jp" in page1.url:
            print(f"[{self.name}] セッション有効 → ログインスキップ")
            self._save_session(page)
            return page1

        user = os.environ.get("MUFGESMART_USER", "")
        password = os.environ.get("MUFGESMART_PASS", "")

        if user and password:
            page1.get_by_role("textbox", name="口座番号").fill(user)
            page1.get_by_role("button", name="次へ").click()
            _wait(1.5, 2.5)
            page1.get_by_role("textbox", name="パスワードを入力").fill(password)
            page1.get_by_role("button", name="ログイン").click()
            _wait(2.0, 3.0)
            self.save_html(page1, "after_credential_submit")
            # OTP または si1.kabu.co.jp のどちらかを待つ
            page1.wait_for_url(
                lambda url: "mfa-email-challenge" in url or "si1.kabu.co.jp" in url,
                timeout=30000,
            )
            _wait(1.0, 2.0)
            if "mfa-email-challenge" in page1.url:
                print(f"[{self.name}] ワンタイム認証コード（メール）を入力してください")
                code = self.prompt("認証コード: ").strip()
                page1.get_by_role("textbox", name="ワンタイム認証コード").fill(code)
                page1.get_by_role("button", name="続ける").click()
                page1.wait_for_url(
                    lambda u: "si1.kabu.co.jp" in u or "members" in u,
                    timeout=60000,
                )
                _wait(2.0, 3.0)
        else:
            print(f"[{self.name}] page1 でログインしてください（口座番号・パスワード・OTP まですべて完了後 Enter）")
            self.prompt("完了後 Enter: ")
            page1.wait_for_url(
                lambda u: "si1.kabu.co.jp" in u or "members" in u,
                timeout=60000,
            )
            _wait(2.0, 3.0)

        # 契約書類再同意画面が挟まる場合は手動操作を促す
        if "KeiyakuSyoruiSaidoui" in page1.url or "Confirm" in page1.url:
            print(f"[{self.name}] 契約書類再同意画面が表示されました。ブラウザで同意操作を完了してください")
            self.prompt("完了後 Enter: ")
            _wait(2.0, 3.0)

        self._save_session(page)
        return page1

    def _navigate_to_pdf_report(self, page1) -> None:
        """報告書等 → PDFReport/Search。

        HAR 確認済み:
          - 「報告書等」→ /members/tradetool/dealingsreport → 302 → PDFReport/Search
        """
        print(f"[{self.name}] 報告書等 → PDFReport/Search へ移動")
        page1.get_by_role("link", name="報告書等").click()
        page1.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.save_html(page1, "pdf_report_search")

    def _set_date_filter(self, page1, target_year: int) -> None:
        """期間フィルターを設定。

        HTML 確認済み（実行後デバッグ HTML 解析）:
          - #Kouhu は visible な select（value="32"=期間指定なし, value="31"=期間指定, 月別オプションあり）
          - 月別オプション例: "2026年01月" (label 固定, value は月次で変動するため label 指定で選択)
          - #fromYMD / #toYMD は igEditor テキスト入力（hidden ではない）
          - #fromY 等は <noscript> 内 → JS 有効時は DOM に存在しない（使用不可）
        """
        issue_year = target_year + 1
        kouhu = page1.locator("#Kouhu")

        # 「{issue_year}年01月」を label 指定で選択（value は月次で変動するため label を使用）
        try:
            kouhu.select_option(label=f"{issue_year}年01月")
            self.dlog(f"Kouhu = {issue_year}年01月")
        except Exception:
            # 月別オプションがない場合は「期間指定なし(すべて)」にフォールバック
            kouhu.select_option("32")
            self.dlog("Kouhu = 期間指定なし(すべて) (フォールバック)")
        _wait(0.5)

    def _set_report_filter(self, page1) -> None:
        """報告書名フィルターを「特定口座年間取引報告書」のみに絞り込む。

        HAR 確認済み:
          - 「報告書名を選択」ボタン → カテゴリ別チェックボックスモーダル
          - 各カテゴリの「全てOFF」を title 属性で選択 → 特定口座年間取引報告書のみチェック → OK
        """
        page1.get_by_role("button", name=re.compile("報告書名を選択")).click()
        _wait(0.5)

        # モーダル内のスコープ（dialog role がある場合）、なければページ全体にフォールバック
        dialog = page1.get_by_role("dialog")
        scope = dialog if dialog.count() > 0 else page1

        for title_text in [
            "取引残高報告書・取引報告書のチェックを全てOFFにします。",
            "その他報告書のチェックを全てOFFにします。",
            "特定口座のチェックを全てOFFにします。",
            "契約書のチェックを全てOFFにします。",
        ]:
            el = scope.get_by_title(title_text)
            if el.count() > 0:
                el.click()
                _wait(0.3)

        scope.get_by_role("checkbox", name="特定口座年間取引報告書").check()
        scope.get_by_role("button", name="OK").click()
        _wait(0.5)

    def _download_pdf(self, page1, target_year: int) -> str | None:
        """検索 → PDF ダウンロード。

        HAR 確認済み:
          - GET /ap/PC/PDFReport/PDFReport/Print?sakuseidate=...&ListId=...&typeFlag=false
          - Content-Disposition: attachment; filename=Report{ListId}_{timestamp}.pdf
          - page1.expect_download() で捕捉（Content-Type = application/octet-stream-dummy でも動作）
          - 特定口座年間取引報告書の行内の PDF リンクを選択
        """
        self._set_date_filter(page1, target_year)
        self._set_report_filter(page1)

        page1.get_by_role("button", name="検索", exact=True).click()
        page1.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.save_html(page1, "after_search")

        # PDF リンクを取得
        # a.thickboxPDF は結果テーブル内のみ存在（フィルターチェックボックス table には無い）
        pdf_link = page1.locator("a.thickboxPDF")
        if pdf_link.count() == 0:
            # フォールバック: "PDF" テキストリンク（codegen 準拠 nth(1)）
            pdf_link = page1.get_by_role("link", name="PDF")
        if pdf_link.count() == 0:
            print(f"[{self.name}] PDF リンクが見つかりません（日付範囲に報告書なし？）")
            return None

        # 結果が複数ある場合は最初のリンク（Kouhu=YYYY年01月 で絞り込み済みのため通常1件）
        target_link = pdf_link.first

        self.prepare_directory()
        filename = f"{target_year}_mufg-esmart_nentori.pdf"

        # PDF リンクは新タブ（Super Visual Formade Print ビューア）で開く。
        # expect_download() は効かないため: popup の URL を取得 → page1.request.get() で直接 PDF bytes 取得
        with page1.expect_popup() as popup_info:
            target_link.click()
        pdf_tab = popup_info.value
        pdf_url = pdf_tab.url
        pdf_tab.close()
        self.dlog(f"PDF URL: {pdf_url}")

        response = page1.request.get(pdf_url)
        pdf_bytes = response.body()
        if not pdf_bytes or pdf_bytes[:4] != b"%PDF":
            print(f"[{self.name}] PDF でないレスポンス: {len(pdf_bytes)} bytes, CT={response.headers.get('content-type', '?')}")
            return None

        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(pdf_bytes)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _collect_core(self, page) -> None:
        year = self.config.get("target_year")
        if year is None:
            raise ValueError("target_year が設定されていません")

        page1 = self._open_trade_page(page)
        self._navigate_to_pdf_report(page1)

        pdf_path = self._download_pdf(page1, year)
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
    parser = argparse.ArgumentParser(description="MUFG eスマート証券 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = MufgEsmartCollector(year=args.year, headless=args.headless, debug=args.debug)
    collector.run()

if __name__ == "__main__":
    main()
