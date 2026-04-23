"""SMBC日興証券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン・2FA・ランダムキーパッドは人間が手動で行う。
    スクリプト起動後、ブラウザでトップ画面まで到達してから Enter を押すこと。
    XML ダウンロード時の取引パスワード入力も人間が行う（認証ボタンはスクリプトが押す）。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

_RE_FILENAME = re.compile(r'filename[^;=\n]*=([^;\n]*)')

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.collector.base import BaseCollector
from money_ops.converter.xml_to_json import convert_teg204_xml

_SITE_JSON = Path(__file__).parent / "site.json"
# 直接ログインフォームへ遷移（www.smbcnikko.co.jp 経由ポップアップは Playwright コンテキスト外になる）
_LOGIN_URL = "https://trade.smbcnikko.co.jp/Login/0/login/ipan_web/hyoji/"


def _wait(lo: float = 1.0, hi: float = 3.0) -> None:
    time.sleep(random.uniform(lo, hi))


class SMBCNikkoCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path)
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/smbcnikko/{year}/raw/"
            self.output_dir = Path(self.config["output_dir"])

    def _wait_for_login(self, page) -> None:
        page.goto(_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        url = page.url
        if isinstance(url, str) and "trade.smbcnikko.co.jp" in url and "/Login/0/login/" not in url:
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            self._session = page
            self.save_html(self._session, "after_login_skip")
            return
        print(f"[{self.name}] ブラウザでログインしてください（ランダムキーパッド・OTP含む）")
        input("トップ画面で操作可能になったら Enter を押してください: ")
        _wait()
        self._session = page
        self.dlog(f"session URL: {self._session.url}")
        self.save_html(self._session, "after_login")

    def _navigate_to_report_list(self) -> None:
        """電子交付履歴ページへ移動・特定口座年間取引報告書で絞り込み・検索"""
        session = self._session
        print(f"[{self.name}] 各種お手続き → 電子交付サービス → 電子交付履歴 へ移動")

        session.get_by_role("link", name="各種お手続き").click()
        session.wait_for_load_state("domcontentloaded")
        _wait()
        self.save_html(session, "after_otetsuzuki")

        # 「電子交付サービス」は同一ページに複数存在（/Etc/…STEP=0 と /MoneyManagement/…STEP=1）
        # href で /MoneyManagement/ かつ STEP=1 を特定する（.nth(N) は状態依存で不安定）
        session.locator("a[href*='e_kofu/denshi_kofu/register'][href*='STEP=1']").first.click()
        session.wait_for_load_state("domcontentloaded")
        _wait()
        self.save_html(session, "after_denshi_kofu")

        # 「電子交付履歴」タブへ（href で特定）
        session.locator("a[href*='denshi_kofu/search']").first.click()
        session.wait_for_load_state("domcontentloaded")
        _wait()
        self.save_html(session, "after_kofu_rekishi")

        session.get_by_role("checkbox", name="特定口座年間取引報告書").check()
        _wait(0.5, 1.0)
        session.get_by_role("row", name="検索", exact=True).get_by_role("button").click()
        session.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.save_html(session, "after_search")

    def _year_month_patterns(self, year: int) -> list[str]:
        """作成日列の年月候補: 対象年12月 or 翌年1月"""
        return [f"{year}/12", f"{year + 1}/01"]

    def _find_xml_link(self, session, year: int):
        """作成日列（th.th05_7）が対象年月にマッチする行から XML リンクを返す"""
        for ym in self._year_month_patterns(year):
            row = session.locator("tr").filter(
                has=session.locator(f"th.th05_7:has-text('{ym}')")
            ).filter(has=session.locator("a[href*='xml/download']"))
            if row.count() > 0:
                return row.first.locator("a[href*='xml/download']").first
        return None

    def _find_pdf_link(self, session, year: int):
        """作成日列（th.th05_7）が対象年月にマッチする行から PDF リンクを返す"""
        for ym in self._year_month_patterns(year):
            row = session.locator("tr").filter(
                has=session.locator(f"th.th05_7:has-text('{ym}')")
            ).filter(has=session.locator("a[href*='trade_report/pdf']"))
            if row.count() > 0:
                return row.first.locator("a[href*='trade_report/pdf']").first
        return None

    def _download_xml(self, session, year: int) -> str | None:
        """XML リンク → 取引パスワードポップアップ（人間入力）→ 認証 → expect_download()"""
        xml_link = self._find_xml_link(session, year)
        if xml_link is None:
            print(f"[{self.name}] XML リンクが見つかりません")
            return None

        with session.expect_popup() as pw_popup_info:
            xml_link.click()
        pw_popup = pw_popup_info.value
        pw_popup.wait_for_load_state("domcontentloaded")
        _wait(2.0, 3.0)
        self.dlog(f"xml popup URL: {pw_popup.url}")
        self.save_html(pw_popup, "xml_pw_popup")

        # 認証後は自動でダウンロードが始まる。expect_download で待機するだけ
        print(f"[{self.name}] ポップアップで取引パスワードを入力し「認証する」をクリックしてください")
        with pw_popup.expect_download(timeout=120000) as dl_info:
            pass
        dl = dl_info.value
        xml_path = self.output_dir / (dl.suggested_filename or f"{year}_nentori.xml")
        dl.save_as(str(xml_path))
        print(f"[{self.name}] XML 保存: {xml_path}")
        pw_popup.close()
        _wait()
        return str(xml_path)

    def _download_pdf(self, session, year: int) -> str | None:
        """PDF リンクの href を取得して直接フェッチ（Chrome 拡張 iframe ボタンは NG）"""
        pdf_link = self._find_pdf_link(session, year)
        if pdf_link is None:
            print(f"[{self.name}] PDF リンクが見つかりません")
            return None

        href = pdf_link.get_attribute("href")
        self.dlog(f"PDF href: {href}")
        # href が javascript:isOpen('/path/to/file.pdf?...') 形式の場合は URL を抽出
        js_match = re.search(r"isOpen\(['\"]([^'\"]+)['\"]", href or "")
        if js_match:
            href = js_match.group(1)
        pdf_url = urljoin("https://trade.smbcnikko.co.jp", href)
        self.dlog(f"PDF URL: {pdf_url}")

        resp = session.context.request.get(pdf_url)
        body = resp.body()
        self.dlog(f"PDF fetch status={resp.status} body[:8]={body[:8]}")
        self.save_response_html(body, "pdf_fetch_response")

        if body[:4] != b"%PDF":
            print(f"[{self.name}] PDF フェッチ失敗（status={resp.status}）")
            return None

        cd = resp.headers.get("content-disposition", "")
        m = _RE_FILENAME.search(cd)
        if m:
            filename = m.group(1).strip().strip('"\'')
        else:
            # SMBC日興は Content-Disposition なし → URL パスのファイル名を使用
            url_filename = Path(urlparse(pdf_url).path).name
            filename = url_filename if url_filename else f"{year}_nentori.pdf"
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(body)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _convert_to_json(self, downloaded_files: list[str]) -> None:
        year = self.config["target_year"]
        xml_files = [f for f in downloaded_files if f.endswith(".xml")]
        if not xml_files:
            print(f"[{self.name}] XML が見つからないため JSON 変換をスキップします")
            return
        raw_files = [str(Path(f).name) for f in downloaded_files]
        data = convert_teg204_xml(
            xml_path=xml_files[0],
            company=self.name,
            code=self.code,
            year=year,
            raw_files=raw_files,
        )
        json_path = self.output_dir.parent / "nenkantorihikihokokusho.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[{self.name}] JSON 保存: {json_path}")

    def collect(self) -> None:
        page = self.launch_browser()
        try:
            self._wait_for_login(page)
            self._save_session_state(page)
            session = self._session
            self._navigate_to_report_list()
            year = self.config["target_year"]

            if self._find_xml_link(session, year) is None:
                self.log_result("skip", [], f"{year}年度の取引報告書が存在しません")
                return

            self.prepare_directory()
            downloaded: list[str] = []

            xml_path = self._download_xml(session, year)
            if xml_path:
                downloaded.append(xml_path)

            pdf_path = self._download_pdf(session, year)
            if pdf_path:
                downloaded.append(pdf_path)

            if not downloaded:
                self.log_result("skip", [], "ダウンロード対象ファイルが見つかりませんでした")
                return

            self._convert_to_json(downloaded)
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
    parser = argparse.ArgumentParser(description="SMBC日興証券 年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    collector = SMBCNikkoCollector(year=args.year)
    collector.collect()


if __name__ == "__main__":
    main()
