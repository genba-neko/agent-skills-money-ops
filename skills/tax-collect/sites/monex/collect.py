"""マネックス証券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）
    DEBUG       true/false（デフォルト: false）

注意:
    ログイン・OTP は人間が手動で行う。
    スクリプト起動後、ブラウザでトップ画面まで到達してから Enter を押すこと。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from money_ops.collector.base import BaseCollector
from money_ops.converter.xml_to_json import convert_teg204_xml

_SITE_JSON = Path(__file__).parent / "site.json"
_LOGIN_URL = "https://mst.monex.co.jp/pc/ITS/login/LoginIDPassword.jsp"


from money_ops.utils import extract_filename, wait as _wait


def _year_month_patterns(target_year: int) -> list[str]:
    """発行年月の候補: 対象年12月 or 翌年1月（日本語表記）"""
    return [f"{target_year}年12月", f"{target_year + 1}年01月"]


class MonexCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path)
        if year is not None:
            self.config["target_year"] = year
            self.config["output_dir"] = f"data/income/securities/monex/{year}/raw/"
            self.output_dir = Path(self.config["output_dir"])

    def _wait_for_login(self, page) -> None:
        page.goto(_LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        url = page.url
        if isinstance(url, str) and "mst.monex.co.jp" in url and "LoginIDPassword" not in url:
            print(f"[{self.name}] ログイン済みを検出 → スキップ")
            return
        print(f"[{self.name}] ブラウザでログインしてください（OTP含む）")
        input("トップ画面で操作可能になったら Enter を押してください: ")
        _wait()
        page.wait_for_load_state("domcontentloaded")
        page.context.storage_state(path=str(self._browser_profile_dir() / "storage_state.json"))
        print(f"[{self.name}] セッション状態を保存しました")

    def _navigate_to_report_list(self, page) -> None:
        """電子交付書面ページへ移動・特定口座年間取引報告書で絞り込む。
        mail OTP を経たパスでは DocSearch に直着するためメニュークリック不要。
        直着しなかった場合のみ「電子交付書面」リンクをクリックする。"""
        self.dlog(f"URL at navigate start: {page.url}")
        self.save_html(page, "before_docsearch")
        if "DocSearch" not in page.url:
            print(f"[{self.name}] 電子交付書面 リンクをクリック")
            # li.nav02（資産・残高管理）をホバーしてドロップダウンを展開してからクリック
            page.locator("li.nav02").hover()
            _wait(0.5, 1.0)
            page.get_by_role("link", name="電子交付書面", exact=True).click()
            page.wait_for_load_state("domcontentloaded")
            _wait()
            self.dlog(f"URL after 電子交付書面 click: {page.url}")
            self.save_html(page, "after_denshi_click")
        print(f"[{self.name}] 特定口座年間取引報告書 で絞り込み")
        page.get_by_text("特定口座年間取引報告書", exact=True).click()
        _wait()
        self.save_html(page, "after_tokutei_filter")
        # 「すべて」表示トグル（最新版のみ → すべて）
        toggle = page.locator(".display-inline-block.width-half.column-right > span > .f-13 > .ico").first
        if toggle.count() > 0:
            toggle.click()
            _wait()
            self.save_html(page, "after_all_toggle")

    def _find_xml_link(self, page, target_year: int):
        """XML リンクを年月パターンで検索"""
        for ym in _year_month_patterns(target_year):
            link = page.get_by_role("link", name=re.compile(re.escape(ym) + r".+XML"))
            if link.count() > 0:
                return link.first
        return None

    def _find_pdf_link(self, page, target_year: int):
        """PDF リンク（XML なし）を年月パターンで検索"""
        for ym in _year_month_patterns(target_year):
            link = page.get_by_role(
                "link", name=re.compile(r"特定口座年間取引報告書" + re.escape(ym))
            ).filter(has_not_text="XML")
            if link.count() > 0:
                return link.first
        return None

    def _download_pdf_via_route(self, page, year: int) -> str | None:
        """PopupのFraAcDocRefer.jspフレームセットからDocDispPdf URLを取得し直接フェッチ（T-14）
        FraAcDocRefer.jsp の frame[name="PDF"] src = DocDispPdf?encodePrm=...
        matsui の AccLogReg.jsp パターンと同構造。context.route() は使わない。"""
        fallback_name = f"{year}_nentori.pdf"

        pdf_link = self._find_pdf_link(page, year)
        if pdf_link is None:
            print(f"[{self.name}] PDF リンクが見つかりません")
            return None

        with page.expect_popup() as pdf_popup_info:
            pdf_link.click()
        pdf_popup = pdf_popup_info.value
        pdf_popup.wait_for_load_state("domcontentloaded")
        _wait()
        self.save_html(pdf_popup, "pdf_popup_FraAcDocRefer")
        self.dlog(f"pdf_popup.url = {pdf_popup.url}")

        # frame[name="PDF"] の src から DocDispPdf URL を取得
        pdf_src = pdf_popup.locator("frame[name='PDF']").get_attribute("src")
        self.dlog(f"frame[PDF] src = {pdf_src}")

        if not pdf_src:
            print(f"[{self.name}] frame[PDF] src が取得できませんでした")
            pdf_popup.close()
            return None

        # 相対パスを絶対 URL に変換
        if pdf_src.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(pdf_popup.url)
            pdf_url = f"{parsed.scheme}://{parsed.netloc}{pdf_src}"
        else:
            pdf_url = pdf_src
        self.dlog(f"DocDispPdf URL = {pdf_url[:120]}")

        pdf_popup.close()

        resp = pdf_popup.context.request.get(pdf_url)
        body = resp.body()
        self.dlog(f"fetch status={resp.status} body[:8]={body[:8]}")
        self.save_response_html(body, "pdf_fetch_response")
        if body[:4] != b"%PDF":
            print(f"[{self.name}] PDF フェッチ失敗（status={resp.status}）")
            return None

        cd = resp.headers.get("content-disposition", "")
        m = _RE_FILENAME.search(cd)
        filename = m.group(1).strip().strip('"\'') if m else fallback_name
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(body)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _download_files(self, page) -> list[str]:
        self.prepare_directory()
        year = self.config["target_year"]
        downloaded: list[str] = []

        xml_link = self._find_xml_link(page, year)
        if xml_link is None:
            print(f"[{self.name}] {year}年度の XML リンクが見つかりません")
            return downloaded

        # XML
        with page.expect_download() as dl_info:
            xml_link.click()
        dl = dl_info.value
        xml_path = self.output_dir / dl.suggested_filename
        dl.save_as(str(xml_path))
        downloaded.append(str(xml_path))
        print(f"[{self.name}] XML 保存: {xml_path}")
        _wait()

        # PDF（context.route で DocDispPdf を捕捉）
        pdf_path = self._download_pdf_via_route(page, year)
        if pdf_path:
            downloaded.append(pdf_path)
            _wait()

        return downloaded

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
            self._navigate_to_report_list(page)

            year = self.config["target_year"]
            if self._find_xml_link(page, year) is None:
                self.log_result("skip", [], f"{year}年度の取引報告書が存在しません")
                return

            downloaded = self._download_files(page)
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
    parser = argparse.ArgumentParser(description="マネックス証券 年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    collector = MonexCollector(year=args.year)
    collector.collect()


if __name__ == "__main__":
    main()
