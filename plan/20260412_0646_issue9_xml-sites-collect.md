# #9 XMLあり各社 Playwright収集スクリプト 実装プラン

## 対象 issue

[#9](https://github.com/genba-neko/agent-skills-money-ops/issues/9) XMLあり各社 Playwright収集スクリプト（楽天証券以外）

---

## 背景・前提知識（操作記録から得た知見）

### ① PDFダウンロード問題

楽天証券・SBI証券・GMOクリック証券は `context.route()` でバイトを捕捉する実装が必要。  
残りの各社は **iframe 内に PDF ビューアを埋め込み + ダウンロードボタン形式** であり、`expect_download()` でキャプチャ可能。

| 会社 | PDF取得方式 |
|---|---|
| 楽天証券（#8 実装済み） | `context.route()` でバイト捕捉 |
| SBI証券 | `context.route("**/DPAW010501020")` でバイト捕捉（e-shishobako ポータル） |
| GMOクリック証券 | `context.route("**/DPAW010501020")` でバイト捕捉（e-shishobako ポータル。SBIと同一） |
| 野村證券 | ポップアップ内 iframe（ランダム name属性） + ダウンロードボタン → `expect_download()` |
| マネックス証券 | ダブルiframe（`frame[name="PDF"]` 内にさらに iframe）+ ダウンロードボタン → `expect_download()` |
| 松井証券 | `context.route("**/ClientPdfOut.jsp**")` でバイト捕捉（iframe ダウンロードボタンは存在しない） |
| SMBC日興証券 | ポップアップ内 iframe（ランダム name属性）+ ダウンロードボタン → `expect_download()` |

> SBI と GMOクリックは共通の e-shishobako ポータル（`plus.e-shishobako.ne.jp`）を使用。  
> PDF は `DPAW010501020` API で配信されるため、iframe の「ダウンロード」ボタンは存在しない。  
> **`frame_locator("iframe").get_by_role("button", name="ダウンロード")` は絶対に使わないこと。**

---

### ② 年間取引報告書の年度表記

年間取引報告書は **対象年度末（12月下旬）〜翌年1月初旬** に発行される。  
発行が12月になる場合は発行年 = `target_year`、1月の場合は `target_year + 1` となり、**`issue_year = target_year + 1` の固定算出は不可**。

**対策**: 発行年月で絞り込む会社については、想定される2パターン — **`{target_year}/12`（12月末発行）** と **`{target_year+1}/01`（翌年1月発行）** — の両方でロケーターを試み、ヒットした方を使う。  
年のみで絞り込むと前年度分の書類にもヒットするため、必ず年月まで含めること。

### 7社 年度絞り込み方式まとめ（2026-04-13 検証・確定）

| 会社 | 年月パターン | 絞り込み方法 | 備考 |
|---|---|---|---|
| **楽天証券** | N/A | `get_by_role("link", name=f"{year}年")` で年度専用サブページへ直遷移 → `tr:has(td span:text-is('{year}'))` で行特定 | ナビゲーション自体が年度指定。最も堅固 |
| **SBI証券** | `{Y}/12` `{Y+1}/01` | キーワード検索「特定口座年間取引報告書」で書類種別を事前フィルタ → `get_by_role("button").filter(has_text=ym)` | キーワード検索が前提。書類名はボタンフィルタに含めない |
| **GMOクリック証券** | `{Y}/12` `{Y+1}/01` | SBI と完全同方式（同一 e-shishobako ポータル） | |
| **松井証券** | `{Y}年12月` `{Y+1}年01月` | `re.compile(r"特定口座年間取引報告書（XMLファイル）" + ym)` — 書類名＋年月を正規表現に含む | 書類名も含むため最も厳密 |
| **マネックス証券** | `{Y}年12月` `{Y+1}年01月` | タブクリックで書類種別を事前フィルタ → 年月＋XML/非XML でリンク特定 | |
| **野村證券** | `{Y}/12` `{Y+1}/01` | `re.compile(ym + r".*特定口座年間取引報告書")` — 年月＋書類名の両方をボタンフィルタで確認 | 年のみでは取引残高報告書等に誤マッチ（実例あり）。書類名必須 |
| **SMBC日興証券** | `{Y}/12` `{Y+1}/01` | 作成日列（`th.th05_7`）の年月でマッチした `<tr>` 行から XML/PDF リンクを個別取得 | href 内部パラメータ（`taisyoY` 等）に依存しない。PDF と XML は別 `<tr>` 行だが同一テーブル内に隣接 |

**SMBC日興 補足**:  
検索結果テーブルは `<tr>` が年度ごとに PDF 行・XML 行の2行ペアで並ぶ（書類名で区別）。  
`_find_xml_link`: `tr:has(th.th05_7:has-text(ym)):has(a[href*='xml/download'])`  
`_find_pdf_link`: `tr:has(th.th05_7:has-text(ym)):has(a[href*='trade_report/pdf'])`  
各行の作成日が `{Y}/12` または `{Y+1}/01` にマッチする行のみを対象とするため、他年度のリンクを拾わない。

---

### ③ ブラウザ起動設定

- `channel="chrome"` は**禁止**（起動中の Chrome プロセスとの干渉リスク・議論済み決定）
- Playwright Chromium のデフォルト GPU は SwiftShader（ソフトウェアレンダラー）のため Canvas/WebGL フィンガープリントが実機 Chrome と異なり、金融サイトに毎回「新デバイス」と判定される
- **`--use-angle=d3d11`** を必ず指定して実機 GPU を使わせること
- **`--disable-blink-features=AutomationControlled`** + **`ignore_default_args=["--enable-automation"]`** で自動化フラグを除去
- `user_agent` の固定指定は不要（`--use-angle=d3d11` があれば UA 偽装より実フィンガープリント一致のほうが効果的）

---

### ④ wait_for_load_state は `domcontentloaded` を使う

金融サイトは WebSocket や常時通信を持つため `networkidle` は永遠に発火しない。  
**`wait_for_load_state` は必ず `"domcontentloaded"` を使うこと。`"networkidle"` は使用禁止。**

---

## 実装 Tips（SBI 実装時のハマり・解決まとめ）

後続実装で同じ失敗をしないための記録。

---

### T-1: ナビゲーションはトップから辿る

**NG**: トップ画面でいきなり「取引報告書等(電子交付)」リンクを探してクリック → Timeout  
**OK**: 口座管理 → 取引報告書等(電子交付) の順に遷移する  
サブメニュー項目はトップ画面では非表示のため、親メニューを先にクリックして展開する必要がある。

---

### T-1b: ホバーで展開するドロップダウンメニューは `.hover()` が必須

**NG**: `get_by_role("link", name="電子交付書面").click()` → 要素が非表示のため Timeout  
**OK**: `page.locator("li.nav02").hover()` → `_wait(0.5, 1.0)` → `get_by_role("link", name="電子交付書面").click()`  
CSS `:hover` トリガーのドロップダウンは JS/CSS が hover 状態を検知して初めて子要素が visible になる。  
`click()` だけでは hover が発火せず、サブメニューが非表示のまま Timeout する。  
**実例**: マネックス証券 `li.nav02`（資産・残高管理）ホバー → 「電子交付書面」リンク表示

---

### T-2: Angular SPA は domcontentloaded では描画が終わっていない

**NG**: `popup.wait_for_load_state("domcontentloaded")` 直後に要素を探す → 見つからない  
**OK**: `popup.wait_for_url("**/dp_apl/usr/**")` + `popup.wait_for_selector("input, button")` + `_wait(2.0, 3.0)` で Angular の初期化完了を待つ  
e-shishobako は Angular SPA で、domcontentloaded 後も JS がコンポーネントを描画中。

---

### T-3: wait_for_selector は非表示要素にマッチして即返る

**NG**: `popup.wait_for_selector("text=PDFファイル")` → ページ上の別要素（非表示含む）にマッチして即返り、アコーディオンが開く前に次へ進む  
**OK**: `popup.locator("button, a").filter(has_text="PDFファイル").first.wait_for(state="visible")` で visible な要素が出るまで待つ

---

### T-4: ボタンは button 要素とは限らない

**NG**: `get_by_role("button").filter(has_text="xmlデータ")` → Angular の `<a>` 要素スタイルボタンがヒットしない  
**OK**: `locator("button, a").filter(has_text="xmlデータ")` で両方を対象にする

---

### T-5: route() は「ポップアップを閉じてから unroute」する（Rakuten 方式）

**NG**: PDF ボタンクリック → `_wait()` → `unroute()` → コンテキストクローズ  
→ unroute 後も pending な route リクエストが残り asyncio エラーが連鎖する  

**OK**: Rakuten の実装と同様に、
1. `context.route()` 登録
2. PDF ボタンクリック → `expect_popup()` でポップアップ取得
3. `pdf_popup.close()` でポップアップを**先に閉じる**
4. `finally: context.unroute()` で登録解除

ポップアップを閉じてから unroute することで pending なリクエストがなくなり、asyncio エラーが発生しない。

---

### T-6: ファイル名はサイト基準（Content-Disposition）で取得する

**NG**: `fallback_name = f"{year}_nentori.pdf"` をハードコードして保存  
**OK**: `response.headers.get("content-disposition")` から filename を正規表現で取得し、取れない場合のみ fallback を使う

---

### T-7: デバッグログに個人情報を出してはいけない

`popup.locator("button, a").all()` 等でページ上の全要素テキストをログ出力すると氏名・口座番号が含まれる。  
**デバッグログは必ず最終コードから削除すること。**

---

### T-8: collect() 内の事前存在チェックはキーワード検索後に行う

**NG**: popup 表示直後（キーワード検索前）に `_find_report_row_button()` を呼んで「存在しない」と判定してスキップ  
**OK**: 存在チェックは `_download_files()` 内でキーワード絞り込み後に行う（または collect() 側では実施しない）

---

### T-9: e-shishobako PDF は context.route() で捕捉する（GMOクリック・SBI共通）

**NG**: `pdf_popup.frame_locator("iframe").get_by_role("button", name="ダウンロード").click()` → Timeout（ボタンは存在しない）  
**OK**: SBI の `_download_pdf_via_route()` を完全コピーする

```python
_RE_FILENAME = re.compile(r'filename[^;=\n]*=([^;\n]*)')  # モジュールレベル必須

popup.context.route("**/DPAW010501020", _capture_pdf)
try:
    with popup.expect_popup() as pdf_popup_info:
        pdf_btn.first.click()
    pdf_popup = pdf_popup_info.value
    pdf_popup.wait_for_load_state("domcontentloaded")
    _wait()
    pdf_popup.close()
finally:
    popup.context.unroute("**/DPAW010501020", _capture_pdf)
```

e-shishobako ポータル（`plus.e-shishobako.ne.jp`）を使う全サイトでこの方式を使うこと。

**URL パターンの注意**: JSP サイトは URL に `;jsessionid=xxx` が付く。glob パターン `**/xxx.jsp**` はセミコロンにマッチしない場合がある。**`re.compile(r"ファイル名キーワード")` の regex パターンを使うと確実**（松井証券で確認済み）。

---

### T-13: JSP サイトの PDF は popup の iframe src を読み取り context.request で直接フェッチする

**根本原因**: Playwright Chromium の組み込み PDF ビューアは CDP ネットワーク層をバイパスするため、
`context.on("response")` / `route()` / `route.fetch()` はいずれも PDF レスポンスを捕捉できない。

**NG**: `context.on("response")`, `context.route()`, `route.fetch()` → すべて「PDF レスポンスを捕捉できませんでした」

**OK**: `pdf_popup.url`（AccLogReg.jsp の URL）からパラメータを取得し、jsessionid をパスに含めた ClientPdfOut.jsp URL を構築して `context.request.get()` で直接フェッチする

```python
with popup.expect_popup() as pdf_popup_info:
    pdf_link.click()
pdf_popup = pdf_popup_info.value
pdf_popup.wait_for_load_state("domcontentloaded")
popup_url = pdf_popup.url  # AccLogReg.jsp;jsessionid=XXX?pdf=...&selectLit=...&listKey=...
pdf_popup.close()

parsed = urlparse(popup_url)
params = parse_qs(parsed.query)
pdf_file   = params["pdf"][0]       # /client3/.../xxx.pdf
select_lit = params["selectLit"][0]
list_key   = params["listKey"][0]

# ★ deal.matsui.co.jp は cookie でなく URL パスの ;jsessionid= でセッション管理
m = re.search(r';jsessionid=([^?&#]+)', popup_url)
jsessionid = m.group(1) if m else ""
jsession_path = f";jsessionid={jsessionid}" if jsessionid else ""

base = f"{parsed.scheme}://{parsed.netloc}"
pdf_url = f"{base}/QC/qcCom/ClientPdfOut.jsp{jsession_path}?selectLit={select_lit}&listKey={list_key}&outPdfFile={pdf_file}"

resp = popup.context.request.get(pdf_url)
body = resp.body()  # body[:4] == b"%PDF" で確認
```

- route/response イベントは PDF ロードをブロックするため**使用禁止**
- jsessionid を URL パスに含めないと status=200 でも HTML が返る（セッション未認証）
- デバッグは `DEBUG=true` で `dlog()` / `save_html()` / `save_response_html()` を使う（BaseCollector 共通機能）

---

### T-14: マネックス証券の PDF は FraAcDocRefer.jsp の frame src から URL を取得して直接フェッチ

**構造**: PDF リンクをクリック → popup が `FraAcDocRefer.jsp?encodePrm=...` で開く（frameset 構成）  
popup 内 `frame[name="PDF"]` の `src` が直接 `DocDispPdf?encodePrm=...` になっている。  
**matsui の AccLogReg.jsp パターンと完全に同じ構造。**

**NG**:
- `frame_locator("frame[name='PDF']").frame_locator("iframe").get_by_role("button", name="ダウンロード").click()` → Chrome 拡張 iframe 内のため Timeout
- `context.route("**/DocDispPdf**", handler)` → Chrome 拡張が PDF を遅延ロードするため route が close_browser() 後に発火し TargetClosedError

**OK**: `frame[name="PDF"]` の `src` 属性を読み取り `context.request.get()` で直接フェッチ

```python
with page.expect_popup() as pdf_popup_info:
    pdf_link.click()
pdf_popup = pdf_popup_info.value
pdf_popup.wait_for_load_state("domcontentloaded")

pdf_src = pdf_popup.locator("frame[name='PDF']").get_attribute("src")
# 相対パス → 絶対 URL に変換
parsed = urlparse(pdf_popup.url)
pdf_url = f"{parsed.scheme}://{parsed.netloc}{pdf_src}"
pdf_popup.close()

resp = pdf_popup.context.request.get(pdf_url)
body = resp.body()  # body[:4] == b"%PDF" で確認
```

**一般則**: frameset 構成の popup は `frame[name="..."].get_attribute("src")` で PDF URL を取得し、`context.request.get()` で直接フェッチする。`context.route()` は使わない。

---

### T-10: Angular SPA の検索は press("Enter")

**NG**: `popup.get_by_role("button").filter(has_text="search").first.click()` → クリックが効かない場合がある  
**OK**: `search_box.press("Enter")` を使う（SBI と同一ポータル）

---

### T-11: 行ボタンは get_by_role("button") で取得する

**NG**: `popup.locator("button, a").filter(has_text=ym)` → `role="button"` の `<div>` 要素を取得できずヒットしない  
**OK**: `popup.get_by_role("button").filter(has_text=ym)` — ARIA ロールで探すと `role="button"` div も対象になる

また行クリック前に `row_btn.scroll_into_view_if_needed()` を呼ぶこと（リストが長い場合に要素が viewport 外にある）。

---

### T-12: ログインURLは取引プラットフォームのトップページを指定する

**NG（GMOクリック）**: `https://www.click-sec.com/...`（ログインページ）  
→ 認証後に取引プラットフォームが別タブで開き、`page` が `about:blank` のままになる。以降の操作が全て失敗する。

**OK**: `https://kabu.click-sec.com/sec2/mypage/top.do`（取引プラットフォームのトップ）  
→ `page.goto()` がこのURLを開くため、ログイン後も `page` が正しいタブを指す。

**一般則**: ログインURLは「ログイン後に操作するページ」を直接指定する。ログインフォームのURLを指定すると認証後に別タブが開いて `page` が取り残されるサイトがある。

---

### ④ 取引なし（報告書未発行）

売却・配当がない年度は報告書自体が発行されないケースがある（操作記録でサンプル確認済み）。

**対策（全社共通）**:  
一覧で対象書類のロケーターが `count() == 0` の場合 → `log_result("skip", [], "対象年度の報告書が存在しません")` で正常終了。

---

## 実装方針

- 楽天証券（#8）の `RakutenCollector` を参考に、各社 `XxxCollector(BaseCollector)` を実装
- 各社共通の PDF ダウンロードヘルパーを `BaseCollector` または共通関数として切り出しを検討
- ログイン方式: **全社共通で人間が手動でログインする**。認証情報はスクリプトに持たせない。
  - スクリプトはログインページを開いた後 `input()` で待機
  - 人間がログイン・2FA・ポップアップ（通知・キャンペーン等）をすべて処理しトップ画面で操作可能な状態になったら Enter
  - Enter 後にスクリプトがナビゲーションを開始する
  - ※ログイン直後に差し込まれるポップアップはタイミング依存で種類が変わるため、スクリプト側では対処しない
- headless 制御: 環境変数 `HEADLESS`（未設定時=false）を踏襲

---

## 各社実装詳細

### SBI証券（sbi）

| 項目 | 内容 |
|---|---|
| ログイン | ログインページを開き人間が手動でログイン・ポップアップ処理・トップ画面到達後 Enter |
| ナビゲーション | 口座管理 → 取引報告書等(電子交付) → 報告書閲覧（ポップアップ） |
| 絞り込み | キーワード検索 `"特定口座年間取引報告書"` → `f"{issue_year}/"` ボタンをクリック |
| XML取得 | `"特定口座年間取引報告書（xmlデータ）"` ボタン → `expect_download()` |
| PDF取得 | `"特定口座年間取引報告書（PDFファイル）"` ボタン → ポップアップ → `iframe` 内ダウンロードボタン → `expect_download()` |
| skip条件 | `f"{issue_year}/"` ボタンが存在しない |

### 野村證券（nomura）

| 項目 | 内容 |
|---|---|
| ログイン | ログインページを開き人間が手動でログイン・ポップアップ処理・トップ画面到達後 Enter |
| ナビゲーション | 口座情報/手続き → 取引報告書等Web交付（ポップアップ）→ 取引パスワード認証 |
| 絞り込み | 発行年月（`f"{target_year}/12"` or `f"{target_year+1}/01"`）＋ `"特定口座年間取引報告書"` で絞り込む（年のみでは取引残高報告書等に誤マッチする） |
| XML取得 | `"特定口座年間取引報告書（xmlデータ）"` ボタン → `expect_download()` |
| PDF取得 | `"特定口座年間取引報告書（PDFファイル）"` ボタン → ポップアップ → `iframe` 内ダウンロードボタン → `expect_download()` |
| skip条件 | `str(target_year)` を含むボタンが存在しない |

### マネックス証券（monex）

| 項目 | 内容 |
|---|---|
| ログイン | ログインページを開き人間が手動でログイン・ポップアップ処理・トップ画面到達後 Enter |
| ナビゲーション | 電子交付書面 → 特定口座年間取引報告書でフィルタ |
| 絞り込み | `f"{issue_year}年"` を含む XML リンク / PDF リンクをそれぞれ取得 |
| XML取得 | `"... XML"` リンク → `expect_download()` |
| PDF取得 | `_download_pdf_via_route()` — `context.route("**/DocDispPdf**")` で捕捉（T-14）。ダブル iframe ダウンロードボタンは**使用禁止**（Chrome 拡張ビューア内のため Playwright から操作不可） |
| skip条件 | `f"{issue_year}年"` を含む XML リンクが存在しない |

### 松井証券（matsui）

| 項目 | 内容 |
|---|---|
| ログイン | ログインページを開き人間が手動でログイン・ポップアップ処理・トップ画面到達後 Enter |
| ナビゲーション | 口座管理 → 電子帳票 → 電子書面閲覧（ポップアップ）→ 特定口座年間取引報告書でフィルタ（すべて表示） |
| 絞り込み | `f"{issue_year}年"` を含む XML リンク |
| XML取得 | `"特定口座年間取引報告書（XMLファイル）{issue_year}年..."` → `expect_download()` |
| PDF取得 | XML なしの同名リンク → ポップアップ → `frame[name="pdfout"]` 内 `iframe` → ダウンロードボタン → `expect_download()` |
| skip条件 | `f"{issue_year}年"` を含む XML リンクが存在しない |

### GMOクリック証券（gmo-click）

| 項目 | 内容 |
|---|---|
| ログインURL | `https://kabu.click-sec.com/sec2/mypage/top.do`（取引プラットフォームのトップ。ログインページ指定はNG） |
| ログイン | 人間が手動でログイン・トップ画面到達後 Enter |
| ナビゲーション | 精算表 → 電子書類閲覧 → `#stockReportLink`（ポップアップ）→ 2FA（セッション次第で出ない場合あり） |
| ポータル待機 | `popup.wait_for_url("**/dp_apl/usr/**")` → Angular SPA 初期化完了（T-2 と同方式） |
| 検索 | `search_box.press("Enter")` でフィルタ（T-10） |
| 行ボタン | `popup.get_by_role("button").filter(has_text=ym)` → `scroll_into_view_if_needed()` → `click()`（T-11） |
| XML取得 | `locator("button, a").filter(has_text="xmlデータ")` → fallback `"XMLデータ"` → `expect_download()` |
| PDF取得 | `_download_pdf_via_route()` — `context.route("**/DPAW010501020")` で捕捉（T-9）。iframe ダウンロードボタンは**使用禁止** |
| skip条件 | `_find_report_row_button()` が None を返す |

### SMBC日興証券（smbcnikko）

| 項目 | 内容 |
|---|---|
| ログイン | ログインページを開き人間が手動でログイン・ポップアップ処理・トップ画面到達後 Enter |
| ナビゲーション | 各種お手続き → 電子交付サービス（`a[href*='register'][href*='STEP=1']`）→ 電子交付履歴 → 書類種別チェックボックス絞り込み → 検索 |
| 絞り込み | 作成日列（`th.th05_7`）が `f"{target_year}/12"` または `f"{target_year+1}/01"` にマッチする `<tr>` 行から XML/PDF リンクを個別取得。`.first` や `href` 内部パラメータには依存しない |
| XML取得 | 対象年月行の XML リンク（`a[href*='xml/download']`）→ 取引パスワード認証ポップアップ（人間操作）→ 認証後に自動ダウンロード → `expect_download(timeout=120000)` で捕捉 |
| PDF取得 | 対象年月行の PDF リンク（`a[href*='trade_report/pdf']`）→ href から `isOpen('/path?...')` を正規表現で抽出 → `urljoin` で絶対 URL 化 → `context.request.get()` で直接フェッチ（`Content-Disposition` なし → URL パスのファイル名を使用） |
| skip条件 | `_find_xml_link()` が None（対象年月の XML 行が存在しない） |

---

## ディレクトリ・ファイル構成（新規追加分）

```
skills/tax-collect/sites/
├── sbi/
│   ├── site.json
│   └── collect.py
├── nomura/
│   ├── site.json
│   └── collect.py
├── monex/
│   ├── site.json
│   └── collect.py
├── matsui/
│   ├── site.json
│   └── collect.py
├── gmo-click/
│   ├── site.json
│   └── collect.py
└── smbcnikko/
    ├── site.json
    └── collect.py
```

---

## 実装進め方

- **DOM確認**: 各社の実装時は事前に取得した操作記録（HTML レスポンス）を参照しながら正確なロケーターを確認する
  - ロールベース（`get_by_role`）が使えない箇所は実際の DOM から CSS セレクターを特定する
  - 操作記録のロケーターはあくまで出発点。実際の DOM と照合して修正する
- **実装順**: 1社ずつ実装・動作確認してから次の会社へ進む（一括実装しない）
  - **動作確認が取れていない会社の次の会社へは絶対に進まない**
  - 動作確認 = 人間が実際にスクリプトを実行し、XML・PDF・JSON が正常に保存されたことを確認すること
  - Claude は動作確認を代行できない。人間が確認して「OK」と伝えるまで次に進まない

## 各社実装・動作確認ステータス

| 会社 | 実装 | 動作確認 |
|---|---|---|
| SBI証券 | 完了（コミット済み） | 完了（2026-04-12） |
| GMOクリック証券 | 完了（コミット済み） | 完了（2026-04-12） |
| 松井証券 | 完了（コミット済み） | 完了（2026-04-12） |
| マネックス証券 | 完了（コミット済み） | 完了（2026-04-12） |
| 野村證券 | 完了（コミット済み） | 完了（2026-04-12） |
| SMBC日興証券 | 完了（コミット済み） | 完了（2026-04-13） |

---

## テスト方針

- **fixtures**: 操作記録から取得した書類一覧ページ等の HTML を匿名化して `tests/fixtures/<会社コード>/` に保存し、ロケーター検証に使用する
- 収集スクリプトのテストは headless=False での手動実行で検証
- `log_result("skip")` の動作はユニットテストで確認

---

## 実装 issue

| # | 内容 | ラベル | 依存 |
|---|---|---|---|
| [#5](https://github.com/genba-neko/agent-skills-money-ops/issues/5) | tax-collect 基盤 | `feat` | [完了 PR#13 2026-04-11] |
| [#6](https://github.com/genba-neko/agent-skills-money-ops/issues/6) | TEG204 XML変換 | `feat` | [完了 PR#14 / bugfix PR#20 2026-04-11] |
| [#8](https://github.com/genba-neko/agent-skills-money-ops/issues/8) | 楽天証券 収集スクリプト | `feat` | [完了 PR#19 2026-04-11] |
| [#9](https://github.com/genba-neko/agent-skills-money-ops/issues/9) | XMLあり各社 収集スクリプト（本プラン） | `feat` | #5 #6 #8 |
