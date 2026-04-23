"""野村證券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン・2FA は人間が手動で行う。
    スクリプト起動後、ブラウザでログインしてトップ画面到達後 Enter を押すこと。
    取引報告書Web交付の取引パスワード入力も人間が行う。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.collector.base import BaseCollector

_SITE_JSON = Path(__file__).parent / "site.json"
_LOGIN_URL = "https://hometrade.nomura.co.jp/web/rmfIndexWebAction.do"


from money_ops.collector.eshishobako import capture_dpaw_pdf
from money_ops.utils import wait as _wait


def _year_month_patterns(target_year: int) -> list[str]:
    """発行年月の候補: 対象年12月 or 翌年1月（GMO-clickと同形式）"""
    return [f"{target_year}/12", f"{target_year + 1}/01"]


class NomuraCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path)
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/nomura/{year}/raw/"
            self.output_dir = Path(self.config["output_dir"])

    def _wait_for_login(self, page) -> None:
        page.goto(_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        url = page.url
        if isinstance(url, str) and "hometrade.nomura.co.jp" in url and "login" not in url.lower():
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            self._session = page
            return
        print(f"[{self.name}] ブラウザでログインしてください（メール認証コード含む）")
        input("トップ画面で操作可能になったら Enter を押してください: ")
        _wait()
        # goto で hometrade.nomura.co.jp へ直接遷移しているため page 自体がセッション
        self._session = page
        self.dlog(f"session URL: {self._session.url}")
        self.save_html(self._session, "after_login")

    def _navigate_to_report_popup(self):
        """取引報告書Web交付ポップアップを開いて e-shishobako SPA が準備完了した状態で返す"""
        session = self._session
        print(f"[{self.name}] 取引報告書等Web交付 へ移動")
        self.save_html(session, "before_report_click")

        # トップ画面に「取引報告書等Web交付」ショートカットが常時存在するため
        # 「口座情報/手続き」クリックは不要。.first で複数マッチを回避
        with session.expect_popup() as popup_info:
            session.get_by_role("link", name=re.compile("取引報告書等")).first.click()
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.dlog(f"report popup URL: {popup.url}")
        self.save_html(popup, "report_popup_before_tradepw")

        print(f"[{self.name}] 取引パスワードを入力・認証後、書類一覧が表示されたら Enter を押してください")
        input("Enter を押してください: ")

        # e-shishobako Angular SPA 初期化完了を待機
        # wait_for_url で dp_apl/usr/ へのルーティング完了を確認後、レンダリング待ち
        # wait_for_selector("input, button") は nomura SPA では visible 判定が合わないため使わない
        popup.wait_for_url("**/dp_apl/usr/**", timeout=30000)
        _wait(3.0, 5.0)
        self.save_html(popup, "report_popup_after_tradepw")
        return popup

    def _find_report_row_button(self, popup, target_year: int):
        """発行年月 + 書類名で対象行ボタンを返す
        ボタンテキスト例: '2026/01/07 特定口座年間取引報告書 2025'
        年月だけでは取引残高報告書等にも誤マッチするため書類名も必須"""
        for ym in _year_month_patterns(target_year):
            btn = popup.get_by_role("button").filter(
                has_text=re.compile(re.escape(ym) + r".*特定口座年間取引報告書")
            )
            if btn.count() > 0:
                return btn.first
        return None

    def _download_files(self, popup) -> list[str]:
        self.prepare_directory()
        year = self.config["target_year"]
        downloaded: list[str] = []

        row_btn = self._find_report_row_button(popup, year)
        if row_btn is None:
            print(f"[{self.name}] {year}年度の報告書が見つかりません")
            return downloaded

        print(f"[{self.name}] 報告書行をクリック（詳細を開く）")
        row_btn.scroll_into_view_if_needed()
        row_btn.click()
        # PDF ダウンロードボタンが visible になるまで待機（T-3）
        popup.locator("button, a").filter(has_text="PDFファイル").first.wait_for(
            state="visible", timeout=15000
        )
        _wait()
        self.save_html(popup, "after_row_click")

        # XML（button または a 要素、T-4）
        xml_btn = popup.locator("button, a").filter(has_text="xmlデータ")
        if xml_btn.count() == 0:
            xml_btn = popup.locator("button, a").filter(has_text="XMLデータ")
        if xml_btn.count() > 0:
            with popup.expect_download() as dl_info:
                xml_btn.first.click()
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

    def collect(self) -> None:
        page = self.launch_browser()
        try:
            self._wait_for_login(page)
            self._save_session_state(page)
            popup = self._navigate_to_report_popup()
            year = self.config["target_year"]

            if self._find_report_row_button(popup, year) is None:
                self.log_result("skip", [], f"{year}年度の取引報告書が存在しません")
                return

            downloaded = self._download_files(popup)
            if not downloaded:
                self.log_result("skip", [], "ダウンロード対象ファイルが見つかりませんでした")
                return

            self._convert_xml_to_json(downloaded)
            self.log_result("success", downloaded)

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
    parser = argparse.ArgumentParser(description="野村證券 年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    collector = NomuraCollector(year=args.year)
    collector.collect()


if __name__ == "__main__":
    main()
