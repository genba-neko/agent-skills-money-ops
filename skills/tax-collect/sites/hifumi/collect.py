"""ひふみ投信 特定口座年間取引報告書（PDF）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン・取引パスワード入力は人間が手動で行う。
    スクリプト起動後、ブラウザでポップアップ（page1）にてログイン完了後 Enter を押すこと。

実測済みポップアップ構造:
    page:  ひふみ トップ（hifumi.rheos.jp）
    page1: ひふみ ログイン・操作画面（123.rheos.jp/wsys/login.jsp）
    page2: e-shishobako（shishyobakoRedirect.do → post.plus.e-shishobako.ne.jp）
           ↑ popup として開き、リダイレクトで e-shishobako Angular SPA になる
           日付ボタン・書類ボタン・PDFファイルボタンはすべて page2 内

PDF取得方式:
    1. page2（e-shishobako）で日付ボタンクリック
    2. 「特定口座年間取引報告書」ボタンクリック → page2 内 Angular ルーター遷移（popup なし）
    3. 「PDFファイル」ボタン → context.route("**/DPAW010501020") 捕捉 → blob popup 閉じる
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from money_ops.collector.base import BaseCollector
from money_ops.converter.pdf_to_json import convert_pdf_to_json

_SITE_JSON = Path(__file__).parent / "site.json"

from money_ops.collector.eshishobako import capture_dpaw_pdf
from money_ops.utils import wait as _wait

def _year_month_patterns(target_year: int) -> list[str]:
    return [f"{target_year}/12", f"{target_year + 1}/01"]

class HifumiCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path, year)

    def _wait_for_login(self, page) -> object:
        """HAR 確認済み:
          - バナー「閉じる」button → 「ログイン」link → popup page1（123.rheos.jp/wsys/login.jsp）
          - loginId + #password_01 → 「ログイン」→ 取引パスワード → 「認証」（すべて手動）
          - page1 URL はログイン後も login.jsp のまま（SPA）
        """
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)

        close_btn = page.get_by_role("button", name="閉じる")
        if close_btn.count() > 0:
            close_btn.first.click()
            _wait(0.5, 1.0)

        with page.expect_popup() as popup_info:
            page.get_by_role("link", name="ログイン").click()
        page1 = popup_info.value
        page1.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.dlog(f"page1 URL: {page1.url}")

        print(f"[{self.name}] page1 でログインしてください（loginId・パスワード・取引パスワード）")
        self.prompt("ログイン完了後 Enter を押してください: ")
        _wait(2.0, 3.0)

        # session cookie 明示保存（persistent profile だけでは session cookie が消える）
        state_path = self._browser_profile_dir() / "storage_state.json"
        page.context.storage_state(path=str(state_path))
        print(f"[{self.name}] セッション保存: {state_path}")

        return page1

    def _navigate_to_eshishobako(self, page1) -> object:
        """page1 で「各種資料（報告書）」→「閲覧する」nth(1) → popup page2。
        page2 は shishyobakoRedirect.do 経由で e-shishobako Angular SPA にリダイレクトされる。

        HAR 確認済み:
          - 「各種資料（報告書）」= link、page1 内遷移（popup なし）
          - 「閲覧する」= link 複数、nth(1) が対象
          - page2 = popup（最終的に post.plus.e-shishobako.ne.jp/dp_apl/usr/#/user-delivery）
        """
        print(f"[{self.name}] 各種資料（報告書）へ移動")
        page1.get_by_role("link", name="各種資料（報告書）").click()
        page1.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        self.save_html(page1, "after_kakushu_shiryo")

        with page1.expect_popup() as popup2_info:
            page1.get_by_role("link", name="閲覧する").nth(1).click()
        page2 = popup2_info.value

        # shishyobakoRedirect.do → e-shishobako Angular SPA へのリダイレクト完了待機
        page2.wait_for_url("**/dp_apl/usr/**", timeout=30000)
        page2.wait_for_selector("input, button", timeout=30000)
        _wait(2.0, 3.0)
        self.dlog(f"page2 URL: {page2.url}")
        self.save_html(page2, "eshishobako_list")
        return page2

    def _find_date_button(self, page2, target_year: int):
        """e-shishobako の日付ボタン（"YYYY/MM/DD" 形式）を YYYY/MM 部分一致で取得。"""
        for ym in _year_month_patterns(target_year):
            btn = page2.get_by_role("button").filter(has_text=re.compile(re.escape(ym)))
            if btn.count() > 0:
                self.dlog(f"日付ボタン発見: ym={ym}")
                return btn.first
        return None

    def _open_report_detail(self, page2, date_btn) -> bool:
        """日付ボタンクリック → 「特定口座年間取引報告書」ボタンクリック。
        ボタンクリックは page2 内の Angular ルーター遷移（popup は開かない）。
        クリック後 「PDFファイル」が visible になるまで待機。
        """
        date_btn.scroll_into_view_if_needed()
        date_btn.click()
        _wait(1.5, 2.5)
        self.save_html(page2, "after_date_button")

        report_btn = page2.get_by_role("button").filter(has_text=re.compile("特定口座年間取引報告書"))
        if report_btn.count() == 0:
            self.dlog("「特定口座年間取引報告書」ボタンが見つかりません")
            return False

        report_btn.first.scroll_into_view_if_needed()
        report_btn.first.click()
        _wait(1.5, 2.5)
        self.save_html(page2, "after_report_button")

        # Angular ルーター遷移後、「PDFファイル」ボタンが visible になるまで待機
        try:
            page2.get_by_role("button").filter(has_text="PDFファイル").first.wait_for(
                state="visible", timeout=15000
            )
        except Exception:
            # fallback: link として存在する場合
            try:
                page2.get_by_role("link").filter(has_text="PDFファイル").first.wait_for(
                    state="visible", timeout=10000
                )
            except Exception:
                self.dlog("「PDFファイル」ボタンが visible になりませんでした")
                return False
        _wait()
        return True

    def _collect_core(self, page) -> None:
        page1 = self._wait_for_login(page)
        year = self.config["target_year"]

        page2 = self._navigate_to_eshishobako(page1)

        date_btn = self._find_date_button(page2, year)
        if date_btn is None:
            self.log_result("skip", [], f"{year}年度の書類が見つかりません（日付ボタン 0件）")
            return

        if not self._open_report_detail(page2, date_btn):
            self.log_result("skip", [], f"{year}年度の特定口座年間取引報告書ボタンが見つかりません")
            return

        self.prepare_directory()
        pdf_path = capture_dpaw_pdf(
            page2, self.output_dir, f"{year}_hifumi_nentori.pdf", label=self.name
        )
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
            print(f"[{self.name}] JSON 変換スキップ（ANTHROPIC_API_KEY 未設定等）: {e}")

        self.log_result("success", [pdf_path])

def main() -> None:
    parser = argparse.ArgumentParser(description="ひふみ投信 特定口座年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None, help="対象年度（例: 2025）")
    args = parser.parse_args()
    collector = HifumiCollector(year=args.year)
    collector.run()

if __name__ == "__main__":
    main()
