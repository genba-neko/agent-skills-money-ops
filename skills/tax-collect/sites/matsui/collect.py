"""松井証券 特定口座年間取引報告書（PDF + XML）Playwright 収集スクリプト

使い方:
    python collect.py [--year YYYY]

環境変数:
    HEADLESS    true/false（デフォルト: false）

注意:
    ログインは人間が手動で行う。
    スクリプト起動後、ブラウザでトップ画面まで到達してから Enter を押すこと。
    サイトはフレーム構成（frameset）のため、ログイン後もフレームが表示されている状態で Enter を押すこと。
"""

from __future__ import annotations

import argparse
import re
from urllib.parse import urlparse, parse_qs
from pathlib import Path

from money_ops.collector.base import BaseCollector

_SITE_JSON = Path(__file__).parent / "site.json"

from money_ops.utils import extract_filename, wait as _wait

def _year_month_patterns(target_year: int) -> list[str]:
    """発行年月の候補: 対象年12月 or 翌年1月（日本語表記）"""
    return [f"{target_year}年12月", f"{target_year + 1}年01月"]

class MatsuiCollector(BaseCollector):
    def __init__(self, site_json_path: str | Path = _SITE_JSON, year: int | None = None):
        super().__init__(site_json_path, year)

    def _wait_for_login(self, page) -> None:
        page.goto(self.config["login_url"])
        print(f"[{self.name}] ブラウザでログインしてください")
        self.prompt("トップ画面（フレーム表示）で操作可能になったら Enter を押してください: ")
        _wait()
        page.context.storage_state(path=str(self._browser_profile_dir() / "storage_state.json"))
        print(f"[{self.name}] セッション状態を保存しました")

    def _navigate_to_report_popup(self, page) -> object:
        """電子書面閲覧ポップアップを開いて返す"""
        print(f"[{self.name}] 口座管理 → 電子帳票 → 電子書面閲覧 へ移動")
        # フレーム構成: frame[name="GM"] に口座管理、frame[name="CT"] に閲覧ボタン
        page.locator("frame[name='GM']").content_frame.get_by_role("cell", name="口座管理", exact=True).click()
        _wait()
        with page.expect_popup() as popup_info:
            page.locator("frame[name='CT']").content_frame.get_by_role("link", name="閲覧する").click()
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded")
        _wait()
        return popup

    def _find_xml_link(self, contents_frame, target_year: int):
        """XML リンクを年月パターンで検索"""
        for ym in _year_month_patterns(target_year):
            link = contents_frame.get_by_role(
                "link", name=re.compile(r"特定口座年間取引報告書（XMLファイル）" + re.escape(ym))
            )
            if link.count() > 0:
                return link.first
        return None

    def _find_pdf_link(self, contents_frame, target_year: int):
        """PDF リンク（XMLファイル なし）を年月パターンで検索"""
        for ym in _year_month_patterns(target_year):
            link = contents_frame.get_by_role(
                "link", name=re.compile(r"特定口座年間取引報告書" + re.escape(ym))
            ).filter(has_not_text="XMLファイル")
            if link.count() > 0:
                return link.first
        return None

    def _download_pdf_via_route(self, pdf_link, popup, year: int) -> str | None:
        """pdf_popup.url（AccLogReg.jsp?pdf=...&selectLit=...&listKey=...）から
        ClientPdfOut.jsp URL を構築し context.request.get() で直接フェッチする。
        route/response/frame は使わない。"""
        fallback_name = f"{year}_nentori.pdf"

        with popup.expect_popup() as pdf_popup_info:
            pdf_link.click()
        pdf_popup = pdf_popup_info.value
        pdf_popup.wait_for_load_state("domcontentloaded")
        popup_url = pdf_popup.url
        self.dlog(f"pdf_popup.url = {popup_url}")
        self.save_html(pdf_popup, "pdf_popup_AccLogReg")
        pdf_popup.close()

        # popup_url = https://www.deal.matsui.co.jp/QC/formDsp/AccLogReg.jsp;jsessionid=...
        #             ?pdf=/client3/.../xxx.pdf&selectLit=6&listKey=...
        parsed = urlparse(popup_url)
        params = parse_qs(parsed.query)
        pdf_file = params.get("pdf", [None])[0]
        select_lit = params.get("selectLit", [None])[0]
        list_key = params.get("listKey", [None])[0]

        self.dlog(f"pdf_file={pdf_file} selectLit={select_lit} listKey={list_key}")

        if not pdf_file:
            print(f"[{self.name}] PDF URL パラメータを取得できませんでした（popup_url={popup_url[:80]}）")
            return None

        # deal.matsui.co.jp は cookie ではなく URL パスの ;jsessionid= でセッション管理
        jsessionid_match = re.search(r';jsessionid=([^?&#]+)', popup_url)
        jsessionid = jsessionid_match.group(1) if jsessionid_match else ""
        self.dlog(f"jsessionid={'あり' if jsessionid else 'なし'}")

        base = f"{parsed.scheme}://{parsed.netloc}"
        jsession_path = f";jsessionid={jsessionid}" if jsessionid else ""
        pdf_url = (
            f"{base}/QC/qcCom/ClientPdfOut.jsp{jsession_path}"
            f"?selectLit={select_lit}&listKey={list_key}&outPdfFile={pdf_file}"
        )
        self.dlog(f"pdf_url = {pdf_url}")

        resp = popup.context.request.get(pdf_url)
        body = resp.body()
        self.dlog(f"fetch status={resp.status} body[:8]={body[:8]}")
        self.save_response_html(body, "pdf_fetch_response")
        if body[:4] != b"%PDF":
            print(f"[{self.name}] PDF フェッチ失敗（status={resp.status}）")
            return None

        cd = resp.headers.get("content-disposition", "")
        filename = extract_filename(cd, fallback_name)
        pdf_path = self.output_dir / filename
        pdf_path.write_bytes(body)
        print(f"[{self.name}] PDF 保存: {pdf_path}")
        return str(pdf_path)

    def _download_files(self, popup) -> list[str]:
        self.prepare_directory()
        year = self.config["target_year"]
        downloaded: list[str] = []

        contents = popup.locator("frame[name='contents']").content_frame

        # 特定口座年間取引報告書でフィルタ（すべて表示）
        contents.get_by_text("特定口座年間取引報告書").click()
        _wait()
        all_radio = contents.get_by_role(
            "row", name="特定口座年間取引報告書 最新版のみ すべて", exact=True
        ).get_by_label("すべて")
        if all_radio.count() > 0:
            all_radio.check()
            _wait()
        contents.get_by_role("button", name="検索").click()
        _wait(2.0, 3.0)

        xml_link = self._find_xml_link(contents, year)
        if xml_link is None:
            print(f"[{self.name}] {year}年度の XML リンクが見つかりません")
            return downloaded

        # XML（直接ダウンロード）
        with popup.expect_download() as dl_info:
            xml_link.click()
        dl = dl_info.value
        xml_path = self.output_dir / dl.suggested_filename
        dl.save_as(str(xml_path))
        downloaded.append(str(xml_path))
        print(f"[{self.name}] XML 保存: {xml_path}")
        _wait()

        # PDF（ClientPdfOut.jsp を context.route() で捕捉）
        pdf_link = self._find_pdf_link(contents, year)
        if pdf_link is not None:
            pdf_path = self._download_pdf_via_route(pdf_link, popup, year)
            if pdf_path:
                downloaded.append(pdf_path)
                _wait()
        else:
            print(f"[{self.name}] PDF リンクが見つかりません")

        return downloaded

    def _collect_core(self, page) -> None:
        self._wait_for_login(page)
        popup = self._navigate_to_report_popup(page)

        downloaded = self._download_files(popup)
        if not downloaded:
            self.log_result("skip", [], "ダウンロード対象ファイルが見つかりませんでした")
            return

        self._convert_xml_to_json(downloaded)
        self.log_result("success", downloaded)

def main() -> None:
    parser = argparse.ArgumentParser(description="松井証券 年間取引報告書収集")
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()
    collector = MatsuiCollector(year=args.year)
    collector.run()

if __name__ == "__main__":
    main()
