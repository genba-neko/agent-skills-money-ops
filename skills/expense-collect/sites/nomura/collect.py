"""野村證券 取引履歴（CSV）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン（店番・口座番号・パスワード）は人間が手動で行う。
    persistent profile 利用で 2 回目以降は cookie 復元 → 即スキップ可能。

実測済みフロー（recorder 確認 output/recorder/nomura/20260427_100250/）:
    1. rmfIndexWebAction.do → 手動ログイン → ダッシュボード
    2. rmfAstTrhTrhLstInitAction.do（取引/注文履歴）へ直接遷移
    3. 期間 select 設定（aselYear/Month/Day, bselYear/Month/Day）
    4. 「照会」 button click → rmfAstTrhTrhLstAction.do
    5. 「CSVダウンロード」 link click → New_file.csv ダウンロード
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from money_ops.collector.base import BaseCollector
from money_ops.utils import wait as _wait

_SITE_JSON = Path(__file__).parent / "site.json"


class NomuraExpenseCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None,
                 headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)

    def _wait_for_login(self, page) -> None:
        """passwd1 input の有無でログイン状態判定。

        login_url 自体が hometrade.nomura.co.jp 配下なので URL ベース判定は誤発火。
        passwd1 が visible = 未ログイン → 手動ログイン待ち
        passwd1 が不可視 = ログイン済み（dashboard）
        """
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        passwd_input = page.locator("input#passwd1")
        if passwd_input.count() == 0 or not passwd_input.is_visible():
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            self.dlog(f"URL: {page.url}")
            return
        print(f"[{self.name}] ブラウザでログイン（店番・口座番号・パスワード）してください（最大5分）")
        # passwd1 が消える（ダッシュボード遷移）まで待機
        passwd_input.wait_for(state="hidden", timeout=300_000)
        _wait()
        self.dlog(f"URL: {page.url}")

    def _navigate_to_history(self, page) -> None:
        """取引/注文履歴画面に直接遷移。"""
        history_url = self.config["history_url"]
        print(f"[{self.name}] 取引履歴画面へ遷移: {history_url}")
        page.goto(history_url)
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        # 期間 select が描画されるまで待機
        page.locator("select#aselYear").first.wait_for(state="visible", timeout=60_000)
        self.dlog(f"history URL: {page.url}")
        self.save_html(page, "trh_lst_init")

    def _set_search_conditions(self, page, year: int, end_month: int = 12, end_day: int = 31) -> None:
        """期間 select 6 個に値設定。"""
        print(f"[{self.name}] 検索条件: {year}/01/01 〜 {year}/{end_month:02d}/{end_day:02d}")
        # 開始: year/01/01
        page.locator("select#aselYear").select_option(value=str(year))
        _wait(0.3, 0.7)
        page.locator("select#aselMonth").select_option(value="01")
        _wait(0.3, 0.7)
        page.locator("select#aselDay").select_option(value="01")
        _wait(0.3, 0.7)
        # 終了: year/end_month/end_day
        page.locator("select#bselYear").select_option(value=str(year))
        _wait(0.3, 0.7)
        page.locator("select#bselMonth").select_option(value=f"{end_month:02d}")
        _wait(0.3, 0.7)
        page.locator("select#bselDay").select_option(value=f"{end_day:02d}")
        _wait(0.5, 1.0)

    def _submit_and_download(self, page) -> str | None:
        """「照会」 click → 結果待ち → 「CSVダウンロード」 link click → CSV 保存。"""
        print(f"[{self.name}] 照会実行")
        page.get_by_role("button", name="照会").first.click()
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)

        # CSV ダウンロード link が visible になるまで待つ
        csv_link = page.get_by_role("link", name="CSVダウンロード").first
        try:
            csv_link.wait_for(state="visible", timeout=30_000)
        except Exception as e:
            self.dlog(f"CSV ダウンロード link 未表示: {e}")
            self.save_html(page, "no_csv_link")
            return None

        self.prepare_directory()
        with page.expect_download(timeout=30_000) as dl_info:
            csv_link.click()
        download = dl_info.value
        suggested = download.suggested_filename or f"nomura_{self.config['target_year']}.csv"
        csv_path = self.output_dir / suggested
        download.save_as(str(csv_path))

        if not csv_path.exists() or csv_path.stat().st_size == 0:
            self.dlog(f"CSV 保存失敗 or 空ファイル: {csv_path}")
            return None
        print(f"[{self.name}] CSV 保存: {csv_path}")
        return str(csv_path)

    def _collect_core(self, page) -> None:
        target_year = self.config["target_year"]
        today = date.today()
        if target_year > today.year:
            raise ValueError(f"未来年は指定不可: {target_year}")

        self._wait_for_login(page)
        self._navigate_to_history(page)

        # 過去年: 1/1 〜 12/31、当年: 1/1 〜 12/31 試行
        self._set_search_conditions(page, target_year, end_month=12, end_day=31)
        csv_path = self._submit_and_download(page)

        # 当年で未来日エラーの可能性 → 今日にフォールバック
        if csv_path is None and target_year == today.year:
            print(f"[{self.name}] 12/31 失敗 → 今日 ({today}) で再試行")
            self._set_search_conditions(page, target_year, end_month=today.month, end_day=today.day)
            csv_path = self._submit_and_download(page)

        if csv_path is None:
            self.log_result("error", [], "CSV 取得失敗")
            return
        self.log_result("success", [csv_path])


def main() -> None:
    parser = argparse.ArgumentParser(description="野村證券 取引履歴（CSV）収集")
    parser.add_argument("--year", type=int, default=None, help="対象年（暦年、例: 2025）")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = NomuraExpenseCollector(year=args.year, headless=args.headless, debug=args.debug)
    sys.exit(collector.run())


if __name__ == "__main__":
    main()
