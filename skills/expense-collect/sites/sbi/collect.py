"""SBI証券 入出金明細（CSV）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン・OTP・デバイス登録は人間が手動で行う。
    スクリプト起動後、ブラウザでログイン完了までユーザーが操作 → site2.sbisec.co.jp 到達を自動検出。

実測済みフロー（recorder 確認）:
    1. www.sbisec.co.jp/ETGate → ログイン → site2.sbisec.co.jp
    2. member.c.sbisec.co.jp/banking/yen/detail-history へ直接遷移
    3. 「最新10明細」 checkbox uncheck → 期間 input fill → 「照会」 click
    4. 「CSVダウンロード」 button click → DetailInquiry_*.csv ダウンロード
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from money_ops.collector.base import BaseCollector
from money_ops.utils import wait as _wait

_SITE_JSON = Path(__file__).parent / "site.json"


class SBIExpenseCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None,
                 headless: bool | None = None, debug: bool | None = None):
        super().__init__(site_json_path, year, headless=headless, debug=debug)
        # BaseCollector は data/income/securities/... を hardcode するので
        # expense 用に上書き
        if year is not None:
            self.output_dir = Path(f"data/expense/{self.code}/{year}/raw/")
            self.config["output_dir"] = str(self.output_dir)

    def _build_date_range(self) -> tuple[str, str]:
        """target_year に応じた検索期間を返す（過去年=1/1〜12/31、当年=1/1〜今日 試行）。
        当年の場合、まず 12/31 試行 → サイト拒否時は今日にフォールバック（呼び出し側で再試行）。
        """
        target_year = self.config["target_year"]
        today = date.today()
        if target_year > today.year:
            raise ValueError(f"未来年は指定不可: {target_year}")
        start = f"{target_year}/01/01"
        if target_year < today.year:
            end = f"{target_year}/12/31"
        else:
            # 当年: まず 12/31 で試行
            end = f"{target_year}/12/31"
        return start, end

    def _wait_for_login(self, page) -> None:
        """tax-collect SBI と同方針: site2.sbisec.co.jp 到達でログイン完了検出。"""
        page.goto(self.config["login_url"])
        page.wait_for_load_state("domcontentloaded")
        _wait(1.5, 2.5)
        if "site2.sbisec.co.jp" in page.url:
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            self.dlog(f"URL: {page.url}")
            return
        print(f"[{self.name}] ブラウザでログイン・OTP・デバイス登録をすべて完了してください（最大5分）")
        page.wait_for_url("**/site2.sbisec.co.jp/**", timeout=300_000)
        _wait()
        self.dlog(f"URL: {page.url}")
        self._save_session_state(page)

    def _navigate_to_history(self, page) -> None:
        """入出金明細画面に直接遷移。"""
        history_url = self.config["history_url"]
        print(f"[{self.name}] 入出金明細画面へ遷移: {history_url}")
        page.goto(history_url)
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        # 「照会」 button が描画されるまで待機（画面構成の主要要素）
        page.get_by_role("button", name="照会").first.wait_for(state="visible", timeout=60_000)
        self.dlog(f"history URL: {page.url}")
        self.save_html(page, "detail_history")

    def _set_search_conditions(self, page, start: str, end: str) -> None:
        """「最新10明細」を uncheck（期間指定モード切替）→ 開始日/終了日 input fill。"""
        print(f"[{self.name}] 検索条件: {start} 〜 {end}")
        # 「最新10明細」 checkbox uncheck
        latest_chk = page.get_by_role("checkbox", name="最新10明細").first
        if latest_chk.is_checked():
            latest_chk.click()
            _wait(0.5, 1.0)

        # 期間 datepicker input は 2 個（開始 / 終了）
        date_inputs = page.locator("div.react-datepicker-wrapper input[type='text']")
        if date_inputs.count() < 2:
            raise RuntimeError(f"期間 input が見つかりません（count={date_inputs.count()}）")

        # fill ではなく click + clear + type の方が React state 反映確実
        for idx, value in [(0, start), (1, end)]:
            inp = date_inputs.nth(idx)
            inp.click()
            inp.fill(value)
            # blur（次の要素 click）で React state commit
            _wait(0.3, 0.7)
        # blur 確定のため照会 button にカーソル移動相当
        page.locator("body").click()
        _wait(0.5, 1.0)

    def _submit_and_download(self, page) -> str | None:
        """「照会」 click → 結果待ち → 「CSVダウンロード」 click → CSV 保存。"""
        print(f"[{self.name}] 照会実行")
        page.get_by_role("button", name="照会").first.click()
        page.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)

        # CSV ダウンロード button が visible になるまで待つ
        csv_btn = page.get_by_role("button", name="CSVダウンロード").first
        try:
            csv_btn.wait_for(state="visible", timeout=30_000)
        except Exception as e:
            self.dlog(f"CSV ダウンロード button 未表示: {e}")
            self.save_html(page, "no_csv_button")
            return None

        self.prepare_directory()
        with page.expect_download(timeout=30_000) as dl_info:
            csv_btn.click()
        download = dl_info.value
        suggested = download.suggested_filename or f"DetailInquiry_{self.config['target_year']}.csv"
        csv_path = self.output_dir / suggested
        download.save_as(str(csv_path))

        if not csv_path.exists() or csv_path.stat().st_size == 0:
            self.dlog(f"CSV 保存失敗 or 空ファイル: {csv_path}")
            return None
        print(f"[{self.name}] CSV 保存: {csv_path}")
        return str(csv_path)

    def _collect_core(self, page) -> None:
        self._wait_for_login(page)
        self._navigate_to_history(page)

        start, end = self._build_date_range()
        self._set_search_conditions(page, start, end)

        csv_path = self._submit_and_download(page)
        # 当年で未来日エラーの可能性 → today にフォールバック試行
        if csv_path is None and self.config["target_year"] == date.today().year:
            today_str = date.today().strftime("%Y/%m/%d")
            print(f"[{self.name}] 12/31 失敗 → 今日 ({today_str}) で再試行")
            self._set_search_conditions(page, start, today_str)
            csv_path = self._submit_and_download(page)

        if csv_path is None:
            self.log_result("error", [], "CSV 取得失敗")
            return
        self.log_result("success", [csv_path])


def main() -> None:
    parser = argparse.ArgumentParser(description="SBI証券 入出金明細（CSV）収集")
    parser.add_argument("--year", type=int, default=None, help="対象年（暦年、例: 2025）")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=None)
    args = parser.parse_args()
    collector = SBIExpenseCollector(year=args.year, headless=args.headless, debug=args.debug)
    sys.exit(collector.run())


if __name__ == "__main__":
    main()
