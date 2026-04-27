"""楽天証券 入出金履歴（CSV）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン（ID・パスワード・絵文字認証・二段階認証）は人間が手動で行う。
    persistent profile 利用で 2 回目以降は cookie 復元 → 即スキップ可能。

実測済みフロー（recorder 確認 output/recorder/rakuten/20260427_134019/）:
    1. MhLogin.do → 手動ログイン（絵文字認証含む） → ダッシュボード
    2. ass_money_trans_lst.do（入出金履歴）に直接遷移
    3. CSV エクスポート link click → Withdrawallist_<YYYYMMDD>.csv ダウンロード
       （1 click で全期間 1515 行 全件取得確認済、ページネーション無視可）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from money_ops.collector.base import BaseCollector
from money_ops.utils import wait as _wait

_SITE_JSON = Path(__file__).parent / "site.json"


class RakutenExpenseCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None,
                 headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _wait_for_login(self, page) -> None:
        """tax-collect/rakuten と同方針: member.rakuten-sec.co.jp/app/ + Login 含まなければ skip。"""
        def _is_dashboard(url: str) -> bool:
            # path 部分のみで判定（query の login_type=1 等を誤検出しないため）
            # /app/Login.do, /app/MhLogin.do, /app/sotp_login.do を除外、
            # /app/home.do, /app/com_page_template.do 等を許可
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if "rakuten-sec.co.jp" not in parsed.netloc:
                return False
            path = parsed.path or ""
            return (
                path.startswith("/app/")
                and "login" not in path.lower()
            )

        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        if _is_dashboard(page.url):
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            self.dlog(f"URL: {page.url}")
            return
        print(f"[{self.name}] ブラウザでログインしてください（絵文字認証・二段階認証含む）（最大10分）")
        page.wait_for_url(lambda url: _is_dashboard(url), timeout=600_000)
        _wait()
        self.dlog(f"URL: {page.url}")

    def _navigate_to_history(self, page) -> None:
        """マイメニュー → 入出金履歴 経由で遷移（BV_SessionID 自動付与のため直接 goto 不可）。"""
        print(f"[{self.name}] マイメニュー → 入出金履歴")
        page.get_by_role("button", name=re.compile("マイメニュー")).click()
        _wait()
        page.get_by_role("link", name="入出金履歴").click()
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        page.locator("form[name='AssMoneyTransLstForm']").first.wait_for(state="visible", timeout=60_000)
        self.dlog(f"history URL: {page.url}")
        self.save_html(page, "money_trans_lst")

    def _submit_and_download(self, page) -> str | None:
        """CSV エクスポート img click → CSV 保存。"""
        print(f"[{self.name}] CSV エクスポート")
        csv_link = page.locator("form[name='AssMoneyTransLstForm'] img.roll").first
        try:
            csv_link.wait_for(state="visible", timeout=30_000)
        except Exception as e:
            self.dlog(f"CSV エクスポート link 未表示: {e}")
            self.save_html(page, "no_csv_link")
            return None

        self.prepare_directory()
        with page.expect_download(timeout=30_000) as dl_info:
            csv_link.click()
        download = dl_info.value
        suggested = download.suggested_filename or f"rakuten_{self.config['target_year']}.csv"
        csv_path = self.output_dir / suggested
        download.save_as(str(csv_path))

        if not csv_path.exists() or csv_path.stat().st_size == 0:
            self.dlog(f"CSV 保存失敗 or 空ファイル: {csv_path}")
            return None
        print(f"[{self.name}] CSV 保存: {csv_path}")
        return str(csv_path)

    def _navigate_to_dividend(self, page) -> None:
        """マイメニュー → 配当・分配金。"""
        print(f"[{self.name}] マイメニュー → 配当・分配金")
        page.get_by_role("button", name=re.compile("マイメニュー")).click()
        _wait()
        page.locator("#megaMenu").get_by_role("link", name="配当・分配金").click()
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        page.locator("form[name='AssDividendHistoryForm']").first.wait_for(state="visible", timeout=60_000)
        self.dlog(f"dividend URL: {page.url}")
        self.save_html(page, "dividend_history")

    def _set_dividend_period(self, page, year: int) -> None:
        """期間 select 設定: year/01/01 〜 year/12/31。"""
        print(f"[{self.name}] 期間設定: {year}/01/01 〜 {year}/12/31")
        page.locator("select#yearFrom").select_option(value=str(year))
        _wait(0.3, 0.7)
        page.locator("select#monthFrom").select_option(value="01")
        _wait(0.3, 0.7)
        page.locator("select#dayFrom").select_option(value="01")
        _wait(0.3, 0.7)
        page.locator("select#yearTo").select_option(value=str(year))
        _wait(0.3, 0.7)
        page.locator("select#monthTo").select_option(value="12")
        _wait(0.3, 0.7)
        page.locator("select#dayTo").select_option(value="31")
        _wait(0.5, 1.0)

    def _submit_and_download_dividend(self, page) -> str | None:
        """配当金画面の CSV エクスポート。

        フロー:
            1. 「表示」 button (input[type=image] onclick='clickSearch()') click
               → eventType=search に設定 + form submit → 期間絞り込み結果表示
            2. CSV エクスポート link (a[onclick='csvOutput()']) click → DL
        """
        print(f"[{self.name}] 表示 button → CSV エクスポート")
        # 「表示」 button click（期間絞り込みを反映するため必須）
        page.locator("form[name='AssDividendHistoryForm'] input[type='image'][onclick*='clickSearch']").first.click()
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)

        csv_link = page.locator("a[onclick*='csvOutput']").first
        try:
            csv_link.wait_for(state="visible", timeout=30_000)
        except Exception as e:
            self.dlog(f"配当金 CSV link 未表示: {e}")
            self.save_html(page, "no_dividend_csv_link")
            return None

        self.prepare_directory()
        with page.expect_download(timeout=30_000) as dl_info:
            csv_link.click()
        download = dl_info.value
        suggested = download.suggested_filename or f"dividendlist_{self.config['target_year']}.csv"
        csv_path = self.output_dir / suggested
        download.save_as(str(csv_path))

        if not csv_path.exists() or csv_path.stat().st_size == 0:
            self.dlog(f"配当金 CSV 保存失敗 or 空ファイル: {csv_path}")
            return None
        print(f"[{self.name}] 配当金 CSV 保存: {csv_path}")
        return str(csv_path)

    def _collect_core(self, page) -> None:
        self._wait_for_login(page)
        paths = []

        # 1. 入出金履歴
        self._navigate_to_history(page)
        p1 = self._submit_and_download(page)
        if p1:
            paths.append(p1)

        # 2. 配当金履歴
        target_year = self.config["target_year"]
        self._navigate_to_dividend(page)
        self._set_dividend_period(page, target_year)
        p2 = self._submit_and_download_dividend(page)
        if p2:
            paths.append(p2)

        if not paths:
            self.log_result("error", [], "両 CSV 取得失敗")
            return
        self.log_result("success", paths)


def main() -> None:
    parser = argparse.ArgumentParser(description="楽天証券 入出金履歴（CSV）収集")
    parser.add_argument("--year", type=int, default=None, help="対象年（暦年、例: 2025）")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = RakutenExpenseCollector(year=args.year, headless=args.headless, debug=args.debug)
    sys.exit(collector.run())


if __name__ == "__main__":
    main()
