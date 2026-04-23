"""大和コネクト証券 特定口座年間取引報告書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS            true/false（デフォルト: false）
    DEBUG               true/false（デフォルト: false）
    DAIWACONNECT_USER   メールアドレス（未設定時は手動入力）
    DAIWACONNECT_PASS   ログインパスワード（未設定時は手動入力）

注意:
    ログイン後の2段階認証コードは必ず手動入力が必要。
    コード入力後 Enter を押すこと。

実測済みページ構造:
    page:  connect-sec.co.jp/service/login/（トップ）
    page1: 大和コネクト証券 SPA（ログイン・操作）
    page2: w37.denshi-bato.webbroker.jp/secdoc/（電子交付サービス）
    page3: w37.denshi-bato.webbroker.jp/seciss/（PDF ビューア）

PDF取得方式:
    context.route("**/denshibato**") で捕捉。
    page3 の PDF ビューアが自動的に GET /seciss/denshibato?SID=... を発行する。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.collector.base import BaseCollector
from money_ops.converter.pdf_to_json import convert_pdf_to_json

_SITE_JSON = Path(__file__).parent / "site.json"
_LOGIN_URL = "https://www.connect-sec.co.jp/service/login/"


from money_ops.utils import wait as _wait


class DaiwaConnectCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path)
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/daiwa-connect/{year}/raw/"
            self.output_dir = Path(self.config["output_dir"])

    def _login(self, page) -> object:
        """connect-sec.co.jp → jumppages/login.html → 認証 → webbroker3。

        HAR 確認済み:
          - section 内リンク → popup page1 (jumppages/login.html)
          - Chromium popup ブロック回避のため直接 goto
          - セッション有効時 → jumppages が webbroker3 へ即リダイレクト（ログインスキップ）
          - セッション無効時 → メールアドレス + パスワード → ログイン → 2段階認証コード
        """
        page.goto(_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        # Chromium で popup が読み込めないため同一ページで直接遷移
        page.goto("https://www.connect-sec.co.jp/jumppages/login.html")
        page1 = page
        page1.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.dlog(f"page1 URL: {page1.url}")

        # セッション有効時は webbroker3 へ即リダイレクトされる
        if "webbroker3" in page1.url:
            print(f"[{self.name}] セッション有効 → ログインスキップ")
            state_path = self._browser_profile_dir() / "storage_state.json"
            page.context.storage_state(path=str(state_path))
            return page1

        user = os.environ.get("DAIWACONNECT_USER", "")
        password = os.environ.get("DAIWACONNECT_PASS", "")

        if user and password:
            page1.get_by_role("textbox", name="メールアドレスを入力").fill(user)
            page1.get_by_role("textbox", name="ログインパスワードを入力").fill(password)
            page1.get_by_role("link", name=re.compile("ログイン")).first.click()
            _wait(2.0, 3.0)
            self.save_html(page1, "after_login1")
            # 2段階認証コード（自動ログイン時のみ）
            if "webbroker3" not in page1.url:
                print(f"[{self.name}] 2段階認証コードを入力してください（メールに届いた6桁）")
                code = input("認証コード: ").strip()
                page1.get_by_role("textbox").first.fill(code)
                page1.get_by_role("link", name=re.compile("ログイン")).first.click()
                _wait(2.0, 3.0)
        else:
            print(f"[{self.name}] ログインしてください（メールアドレス・パスワード・2段階認証まですべて完了後 Enter）")
            input("完了後 Enter: ")

        # webbroker3 SPA の読み込み完了を待つ
        page1.wait_for_url("**/webbroker3/**", timeout=30000)
        _wait(2.0, 3.0)
        self.dlog(f"page1 after login URL: {page1.url}")

        state_path = self._browser_profile_dir() / "storage_state.json"
        page.context.storage_state(path=str(state_path))
        print(f"[{self.name}] セッション保存: {state_path}")
        return page1

    def _open_electronic_delivery(self, page1) -> object:
        """お客様情報 → 電子交付サービス → popup page2。

        HAR 確認済み:
          - 「お客様情報」link → page1内遷移
          - 「電子交付サービス」link → popup page2（w37.denshi-bato）
        """
        print(f"[{self.name}] お客様情報 → 電子交付サービスへ移動")
        # sidrToggle（モバイル用不可視）を除外して本体ナビをクリック
        page1.locator("ul.navbar-nav a:not(.sidrToggle)", has_text="お客様情報").click()
        page1.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        # 暗証番号入力ページが挟まる場合はブラウザで入力する
        # BatoSubmitHome が定義されていれば電子交付サービスが表示済み
        print(f"[{self.name}] 暗証番号等の追加認証が必要な場合はブラウザで入力してください")
        page1.wait_for_function("typeof BatoSubmitHome === 'function'", timeout=60000)

        # BatoSubmitHome() が電子交付サービス popup を開く JS 関数
        with page1.expect_popup() as popup2_info:
            page1.evaluate("BatoSubmitHome()")
        page2 = popup2_info.value
        page2.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.save_html(page2, "eshishobako_list")
        return page2

    def _navigate_to_annual_report(self, page2) -> None:
        """page2: 年間取引報告書カテゴリを選択 → フィルター → 検索。

        HAR 確認済み:
          - 「取引残高報告書/ 年間取引報告書/支払通知書/ NISA」行のリンク
          - 書類種別 select option "3"、期間 select option "2"
          - 「未読・既読を表示」チェック → 検索
        """
        page2.get_by_role("row", name=re.compile("年間取引報告書")).get_by_role("link").first.click()
        page2.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.save_html(page2, "after_row_click")

        # 書類種別フィルター（option 3 = 特定口座年間取引報告書）
        doc_cell = page2.get_by_role("cell", name=re.compile("取引残高報告書"))
        if doc_cell.count() > 0:
            doc_cell.first.locator("span").first.click()
            _wait(0.5)
            doc_cell.first.get_by_role("combobox").select_option("3")
            _wait(0.5)

        # 期間フィルター（option 2）
        period_cell = page2.get_by_role("cell", name=re.compile("前月初め"))
        if period_cell.count() > 0:
            period_cell.first.get_by_role("combobox").select_option("2")
            _wait(0.5)

        # 未読・既読を表示チェック
        show_all = page2.get_by_text("未読・既読を表示")
        if show_all.count() > 0:
            show_all.first.click()
            _wait(0.5)

        page2.get_by_role("link", name="検索").click()
        page2.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.save_html(page2, "after_search")

    def _download_pdf_via_route(self, page2, target_year: int) -> str | None:
        """年間取引報告書リンク → page3(PDF viewer) → route 捕捉。

        HAR 確認済み:
          - 「年間取引報告書」link → popup page3（PDF ビューア）
          - page3 が GET /seciss/denshibato?SID=...&FROMSCREEN=CuRefBalL を発行
          - route で application/pdf を捕捉
          - page2 は /seciss/denshibato へ遷移（セッション更新のため）
        """
        pdf_bytes_holder: list[tuple[str, bytes]] = []
        fallback_name = f"{target_year}_daiwa-connect_nentori.pdf"

        def _capture_pdf(route, request) -> None:
            response = route.fetch()
            body = response.body()
            ct = response.headers.get("content-type", "")
            if "pdf" in ct.lower() or body[:4] == b"%PDF":
                pdf_bytes_holder.append((fallback_name, body))
            route.fulfill(response=response)

        page2.context.route("**/denshibato**", _capture_pdf)
        try:
            # 年間取引報告書リンクをクリック → page3 popup
            report_link = page2.get_by_role("link", name=re.compile("年間取引報告書"))
            if report_link.count() == 0:
                self.dlog("年間取引報告書リンクが見つかりません")
                return None

            with page2.expect_popup() as page3_info:
                report_link.first.click()
            page3 = page3_info.value
            page3.wait_for_load_state("domcontentloaded")
            _wait(2.0, 3.0)

            # page2 を /seciss/denshibato に遷移（codegen準拠、セッション更新）
            page2.goto("https://w37.denshi-bato.webbroker.jp/seciss/denshibato")
            _wait(2.0, 4.0)

            page3.close()
        finally:
            page2.context.unroute("**/denshibato**", _capture_pdf)

        if not pdf_bytes_holder:
            self.dlog("PDF レスポンスを捕捉できませんでした")
            return None

        self.prepare_directory()
        filename, pdf_bytes = pdf_bytes_holder[0]
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(pdf_bytes)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def collect(self) -> None:
        page = self.launch_browser()
        try:
            page1 = self._login(page)
            year = self.config["target_year"]

            page2 = self._open_electronic_delivery(page1)
            self._navigate_to_annual_report(page2)

            pdf_path = self._download_pdf_via_route(page2, year)
            if pdf_path is None:
                self.log_result("error", [], "PDF 捕捉失敗")
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

        except KeyboardInterrupt:
            print(f"\n[{self.name}] ユーザーによる中断")
            self.log_result("interrupted", [], "ユーザーによる中断")
        except Exception as e:
            print(f"[{self.name}] エラー: {e}")
            self.log_result("error", [], str(e))
            raise
        finally:
            self.close_browser()


def main() -> None:
    parser = argparse.ArgumentParser(description="大和コネクト証券 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    args = parser.parse_args()
    collector = DaiwaConnectCollector(year=args.year)
    collector.collect()


if __name__ == "__main__":
    main()
