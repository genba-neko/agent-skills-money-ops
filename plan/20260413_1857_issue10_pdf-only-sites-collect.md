# #10 PDFのみ各社 Playwright収集スクリプト 実装プラン [完了 PR#XX 2026-04-23]

## 対象 issue

[#10](https://github.com/genba-neko/agent-skills-money-ops/issues/10) PDFのみ各社 Playwright収集スクリプト

---

## 対象会社（全7社・PDFのみ・XMLなし）

| code | 会社名 | HAR+codegen |
|---|---|---|
| mufg-esmart | 三菱UFJ eスマート証券 | あり |
| tsumiki | tsumiki証券 | あり |
| daiwa-connect | 大和CONNECT証券 | あり |
| paypay | PayPay証券 | あり |
| nomura-mochikabu | 野村證券持株会 | あり |
| hifumi | ひふみ投信 | あり |
| sawakami | さわかみ投信 | あり（PDFダウンロード操作は未記録） |

> セゾンポケット: 2025年度をもって廃止のため対象外。

---

## #9 実装済み知見の引き継ぎ（重要）

本 issue は PDF のみのサイトのため、XML 取得・`convert_teg204_xml` は不要。  
ただし、以下の #9 Tips はすべて適用する。

| Tip | 内容（要約） |
|---|---|
| T-1 | ナビゲーションはトップから辿る（サブメニューを先に展開） |
| T-1b | ホバーで展開するメニューは `.hover()` 必須 |
| T-2 | Angular SPA は domcontentloaded 後に追加待機 |
| T-3 | wait_for_selector ではなく `.wait_for(state="visible")` を使う |
| T-4 | ボタンは `button, a` 両方を対象にする |
| T-5 | route() はポップアップを閉じてから unroute |
| T-6 | ファイル名は Content-Disposition から取得、取れない場合のみ fallback |
| T-7 | デバッグログに個人情報を出さない |
| T-8 | 存在チェックは書類一覧表示後（絞り込み後）に行う |
| T-10 | Angular SPA の検索は press("Enter") |
| T-11 | 行ボタンは `get_by_role("button")` で取得し、`scroll_into_view_if_needed()` |
| T-12 | ログインURLは「ログイン後に操作するページ」を指定 |

**今 issue での新知見（実装時に追記していく）**: T-15 以降。

---

## PDFダウンロード方式の分類

今 issue の全社は e-shishobako ポータル（DPAW010501020）を使わない。

### ⚠️ iframe ダウンロードボタン方式の前提条件

`frame_locator("iframe").get_by_role("button", name="ダウンロード")` + `expect_download()` が使えるのは、  
**ポップアップが通常の HTML ページ（iframe を含む PDF ビューア）として完全にロードされる場合のみ**。

ポップアップが直接 `application/pdf` を返す URL に遷移する場合、Chrome 内蔵 PDF ビューアが  
CDP ネットワーク層をバイパスするため、`route()` / `response` イベント / iframe 操作はいずれも機能しない。  
→ **T-13方式（`context.request` 直接フェッチ）を使うこと。**

### nomura-mochikabu で確定した方式（2026-04-13）

`weachouhyou.jsp` は `onload` で `ChouhyouDisplayPost.do`（application/pdf を返す）に自動 POST する構造。  
ポップアップが `ChouhyouDisplayPost.do` に遷移した瞬間、Chrome PDF ビューアが介入し  
Playwright の navigation が完了しない（= wait_for / iframe / route すべて不能）。

**正解**: `report_link.get_attribute("href")` で JSP URL を取得 →  
`page.context.request.get(jsp_url)` でHTMLをフェッチ →  
hidden input をパース → `context.request.post(ChouhyouDisplayPost.do)` でPDF直接取得。  
ポップアップを一切開かない。

### 各社 PDF 取得方式

| 会社 | PDF取得方式 |
|---|---|
| 三菱UFJ eスマート証券 | 検索結果リスト「PDF」リンク → `expect_download()` 直接DL（ポップアップなし） |
| tsumiki証券 | ポップアップ → iframe（name属性ランダム）→「ダウンロード」ボタン → `expect_download()` |
| 大和CONNECT証券 | ポップアップ → iframe（name属性ランダム）→「ダウンロード」ボタン → `expect_download()` |
| PayPay証券 | メインページ内 ダブルiframe →「ダウンロード」ボタン → `expect_download()` |
| 野村證券持株会 | **T-13方式**: `context.request.get(weachouhyou.jsp)` → hidden input パース → `context.request.post(ChouhyouDisplayPost.do)` |
| ひふみ投信 | ポップアップ → iframe（name属性ランダム）→「ダウンロード」ボタン → `expect_download()` ※HAR確認後に変更の可能性あり |
| さわかみ投信 | XHR POST `/e-delivery?handler=Download` → blob → `Utils.localDownload()` → `<a download>` click → `page.expect_download()` で捕捉 |

**iframe name属性はセッションごとに変わるため、nameでは指定しない。**  
`frame_locator("iframe").get_by_role("button", name="ダウンロード")` で取得する。

---

## 年度絞り込み方式まとめ

| 会社 | 絞り込み方法 |
|---|---|
| 三菱UFJ eスマート証券 | 期間 `{Y}/12/01 〜 {Y+1}/01/31` + 「特定口座年間取引報告書」チェックボックスのみON |
| tsumiki証券 | ボタンテキスト「特定口座年間取引報告書」+ 作成日 `{Y}/12` or `{Y+1}/01` |
| 大和CONNECT証券 | combobox 種類=「年間取引報告書」+ 「年間取引報告書」リンクテキスト（年度含む） |
| PayPay証券 | 「電子交付書類」一覧テーブルから「特定口座年間取引報告書」行を特定 |
| 野村證券持株会 | `#chohyoType=3`（特定口座年間取引報告書）でフィルタ後、書類リンクの年度テキスト |
| ひふみ投信 | 日付ボタン `{Y}/12/xx` or `{Y+1}/01/xx` + 「特定口座年間取引報告書」ボタン |
| さわかみ投信 | 「特定口座年間取引報告書」チェック + 受信日期間指定（datepicker） |

---

## HAR起点の実装方針（重要）

**codegen（.py）は補助情報に過ぎない。** 操作の記録漏れ・誤クリック・ハードコード認証情報が混入しており、そのまま実装の根拠にしてはならない。

実装の流れ:
1. **HAR を最初に読む** — どのURLに何のリクエストが飛び、レスポンスがどんな構造か確認する
2. **codegen で操作の大まかな流れを把握** — ページ遷移・ポップアップ発生タイミング等
3. **食い違いは HAR を正とする** — codegen に存在する操作でも HAR に対応するリクエストがなければ不要な操作と判断してよい
4. **PDF ダウンロードは特に HAR で確認** — `Content-Type: application/pdf` のリクエストを追い、URL・ヘッダー・クッキーを把握してから実装する

codegen の既知の不足・問題点:
- **sawakami**: PDF ダウンロード操作が完全未記録
- **mufg-esmart**: カレンダーUI の操作手順が不明確（`#fromYMD` 直接 fill できるか未確認）
- **daiwa-connect**: `page2.goto()` はrecording時の誤操作の疑いあり（HARで確認）
- **nomura-mochikabu**: `#chohyoType=3` が「特定口座年間取引報告書」に対応するか未確認（HARで確認）
- **hifumi**: `閲覧する` の nth(1) がどの書類に対応するか不明（HARで確認）

---

## PDF → JSON 変換方針

issue #7 実装済みの `convert_pdf_to_json()` を使用する。

| サイト | 収集書類 | PDF→JSON変換 |
|---|---|---|
| mufg-esmart | 特定口座年間取引報告書 | **あり**（`convert_pdf_to_json()` を呼ぶ） |
| tsumiki | 特定口座年間取引報告書 | **あり** |
| daiwa-connect | 年間取引報告書 | **あり** |
| paypay | 特定口座年間取引報告書 | **あり** |
| hifumi | 特定口座年間取引報告書 | **あり** |
| sawakami | 特定口座年間取引報告書 | **あり** |
| nomura-mochikabu | **配当金等支払通知書** | **なし**（スキーマが異なる） |

変換ありのサイトは `collect()` 内でPDFダウンロード後に以下を呼ぶ:
```python
from money_ops.converter.pdf_to_json import convert_pdf_to_json

data = convert_pdf_to_json(
    pdf_path=pdf_path,
    company=self.name,
    code=self.code,
    year=year,
    raw_files=[pdf_path],
)
json_path = self.output_dir.parent / "nenkantorihikihokokusho.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

---

## 実装共通方針

- `BaseCollector` を継承する（`launch_browser`, `log_result`, `save_html`, `dlog` 等を活用）
- ログイン: **全社共通で人間が手動**。スクリプトはログインURLを開いて `input()` で待機
- `_wait(lo, hi)` で操作間に 1〜3秒のランダムウェイト
- headless: 環境変数 `HEADLESS`（未設定時=false）
- `--use-angle=d3d11` / `--disable-blink-features=AutomationControlled` / `ignore_default_args=["--enable-automation"]` は BaseCollector に実装済みのため collect.py では不要
- `wait_for_load_state("networkidle")` 使用禁止 → `"domcontentloaded"` を使う
- `channel="chrome"` 使用禁止
- has_xml=false のためXML取得・JSON変換は不要
- `_convert_to_json()` は実装しない
- skip 条件: 対象書類のロケーターが `count() == 0` → `log_result("skip", [], "...")`

---

## 各社実装詳細

### 1. nomura-mochikabu（野村證券持株会）

| 項目 | 内容 |
|---|---|
| login_url | `https://www.e-plan.nomura.co.jp/login/index.html` |
| ログイン | メールアドレス + パスワード → ログイン → ポップアップ「閉じる」 → 手動完了後 Enter |
| ナビゲーション | 「Web交付」リンク → `#chohyoType` select で「3」（特定口座年間取引報告書）選択 → `goto(WEAW1200.jsp)` |
| 書類特定 | `get_by_role("link")` で `str(target_year)` を含むリンクを絞り込み（`#chohyoType=3` で帳票種別フィルタ済み） |
| PDF取得 | リンクをクリック → ポップアップ → `frame_locator("iframe").get_by_role("button", name="ダウンロード")` → `expect_download()` |
| skip条件 | 書類リンクが 0件 |
| 備考 | codegenでは「配当金等支払通知書」を選択していたが、`#chohyoType=3` に設定すれば「特定口座年間取引報告書」のみ表示される（実装時に確認） |

---

### 2. hifumi（ひふみ投信）

| 項目 | 内容 |
|---|---|
| login_url | `https://hifumi.rheos.jp/`（トップ） |
| ログイン | トップのバナー「閉じる」→「ログイン」クリック → ポップアップ（page1）→ loginId + password → 取引パスワード（別フォーム）→ 認証 → 手動完了後 Enter |
| ナビゲーション | page1 で「各種資料（報告書）」→「閲覧する」クリック → ポップアップ（page2） |
| 書類特定 | page2 に日付ボタン一覧が表示される → `get_by_role("button").filter(has_text=re.compile(ym))` で `{Y}/12` or `{Y+1}/01` にマッチする日付ボタンをクリック |
| PDF取得 | 日付ボタンクリック後、「特定口座年間取引報告書送付のご案内（PDFファイル）」ボタン → ポップアップ（page3）→ `frame_locator("iframe").get_by_role("button", name="ダウンロード")` → `expect_download()` |
| skip条件 | 日付ボタンが 0件、または「特定口座年間取引報告書」ボタンが 0件 |
| 備考 | codegenの「閲覧する」は nth(1) だが、実装では書類種別で絞り込む。ポップアップは 3層（page1: メイン, page2: 書類一覧, page3: PDF） |

---

### 3. tsumiki（tsumiki証券）

| 項目 | 内容 |
|---|---|
| login_url | `https://www.tsumiki-sec.com/`（トップ） |
| ログイン | 「ログイン」クリック → ポップアップ（page1）→ エポスNet ID + パスワード → ログイン → 広告ポップアップ「閉じる」→ ワンタイムパスワード → 手動完了後 Enter |
| ナビゲーション | page1 で「メニュー画面を開く」→「資産の状況を見る」→「お取引に関する報告書（電子書面）」→ ワンタイムパスワード認証（手動） |
| 書類特定 | 書類ボタン一覧から `get_by_role("button").filter(has_text="特定口座年間取引報告書").filter(has_text=re.compile(ym))` で `{Y}/12` or `{Y+1}/01` を含むボタンを特定 |
| PDF取得 | 書類ボタンクリック → ポップアップ（page2）→ `frame_locator("iframe").get_by_role("button", name="ダウンロード")` → `expect_download()` |
| skip条件 | 対象ボタンが 0件 |
| 備考 | ワンタイムパスワードが「お取引に関する報告書」アクセス時に要求される。これも手動入力 → スクリプトは Enter 待機を2回設ける（ログイン後・報告書認証後） |

---

### 4. daiwa-connect（大和CONNECT証券）

| 項目 | 内容 |
|---|---|
| login_url | `https://www.connect-sec.co.jp/service/login/` |
| ログイン | 「PCブラウザでご利用」リンク → ポップアップ（page1）→ メールアドレス + パスワード → ログイン → 6桁2FA → 手動完了後 Enter |
| ナビゲーション | page1 で「お客様情報」→「電子交付サービス」→ ポップアップ（page2、denshi-bato ポータル） |
| 絞り込み | page2 で「取引残高報告書/ 年間取引報告書/...」行リンク → 種類 combobox で「年間取引報告書」相当の option を選択 → 期間 combobox を全件に → 検索 |
| 書類特定 | 「年間取引報告書」リンクを `get_by_role("link").filter(has_text=re.compile(str(target_year)))` で年度絞り込み |
| PDF取得 | リンククリック → ポップアップ（page3）→ `frame_locator("iframe").get_by_role("button", name="ダウンロード")` → `expect_download()` |
| skip条件 | 「年間取引報告書」リンクが 0件 |
| 備考 | comboboxのoption値（「3」）は年間取引報告書に対応する可能性が高いが実装時に確認。`page2.goto()` はcodegenの誤記録の可能性が高いため、page3を閉じた後に `page2.go_back()` or 再検索する |

---

### 5. paypay（PayPay証券）

| 項目 | 内容 |
|---|---|
| login_url | `https://www.paypay-sec.co.jp/`（トップ） |
| ログイン | 「ログイン」→「PC取引画面へログイン」→ 会員ID + パスワード → ログイン → SMS 6桁 → 手動完了後 Enter |
| ナビゲーション | 「メニュー」→「電子交付書類」 |
| 書類特定 | 電子交付書類一覧テーブルから「特定口座年間取引報告書」を含む行を `get_by_role("row").filter(has_text="特定口座年間取引報告書").filter(has_text=str(target_year))` で特定 |
| PDF取得 | 行の PDFアイコン（td の img）クリック → インライン iframe ビューア表示 → `frame_locator("iframe").frame_locator("iframe").get_by_role("button", name="ダウンロード")` → `expect_download()` → 「閉じる」ボタン |
| skip条件 | 「特定口座年間取引報告書」行が 0件 |
| 備考 | ダブルiframe（外側 iframe: PDF ビューア、内側 iframe: ダウンロードボタン）。ポップアップは開かずメインページ内で完結 |

---

### 6. mufg-esmart（三菱UFJ eスマート証券）

| 項目 | 内容 |
|---|---|
| login_url | `https://kabu.com/`（トップ。registryのlogin_url=null） |
| ログイン | 「ログイン」リンク → ポップアップ（page1）→ 口座番号 → 次へ → パスワード → ログイン → ワンタイム認証コード（2FA）→ 手動完了後 Enter |
| ナビゲーション | page1 で「報告書等」→「こちら」リンク → ポップアップ（page2）が開くが即 close → page1 の電子交付書面閲覧画面で操作 |
| 絞り込み | 期間指定: `#fromYMD` に `{Y}/12/01`、`#toYMD` に `{Y+1}/01/31` を `.fill()` または JavaScript で直接入力 → カレンダーUI操作（実装時に確認） |
| 報告書種別 | 「報告書名を選択」ボタン → 「取引残高報告書・取引報告書」「その他報告書」「特定口座」「契約書」チェックOFF → 「特定口座年間取引報告書」のみチェックON → OK |
| 書類特定 | 「検索」ボタン → 結果テーブルの「PDF」リンク → `get_by_role("link", name="PDF")` の先頭（nth(0) または first） |
| PDF取得 | `expect_download()` で直接DL（ポップアップなし） |
| skip条件 | 「PDF」リンクが 0件 |
| 備考 | page2（ポップアップ）の目的はcodegenから不明だが、開いて即 close で問題なし（操作過程に含まれる）。期間指定UIがカレンダー形式のため `.fill()` で直接値を入れられるかが実装の鍵 |

---

### 7. sawakami（さわかみ投信）[完了 2026-04-23]

| 項目 | 内容 |
|---|---|
| login_url | `https://fv.sawakami.co.jp/Account/Login` |
| ログイン | ログインID + ログインパスワード → ログイン → メール認証コード（spinbutton "認証コード"）→ 認証する |
| ナビゲーション | 直接 `/e-delivery?sf=Inbox&fo=Unopened&fo=Opened&dd_f={Y+1}/01/01&rep_ty=03` へ URL ナビゲーション（UI操作不要） |
| 書類特定 | `.contents-item` を `has_text="特定口座年間取引報告書"` + `has_text=str(issue_year)` でフィルタ |
| PDF取得 | `a.x-shadowButton.x-m-download` クリック → XHR POST `/e-delivery?handler=Download` → blob → `Utils.localDownload()` → `<a download>` → `page.expect_download()` |
| skip条件 | `.contents-item` が 0件（書類未発行の場合） |
| 備考 | rep_ty=03 が UI で disabled でも URL 直指定でフィルタ可能。セッションチェックは URL だけでは不十分（未認証でも `/e-delivery?sf=Inbox...` にリダイレクトしログインフォームを表示）。`input[name="Input.LoginId"]` の存在で判定する。 |

---

## 実装順序

シンプルなものから着手し、1社ずつ動作確認してから次へ進む。

1. **nomura-mochikabu** — iframe ダウンロード・combobox フィルタのみ。構造が最もシンプル
2. **hifumi** — 日付フォルダ選択 + iframe ダウンロード。3層ポップアップだが操作は直線的
3. **tsumiki** — ボタンテキスト絞り込み + iframe ダウンロード。ワンタイムパスワードが2回必要
4. **daiwa-connect** — denshi-bato ポータル + combobox 絞り込み + iframe ダウンロード
5. **paypay** — ダブルiframe + メインページ内完結。iframe 入れ子の動作確認が必要
6. **mufg-esmart** — 期間指定カレンダー + チェックボックスフィルタ + 直接DL。操作が最も複雑
7. **sawakami** — datepicker が脆弱 + PDF取得方式が不明。最後に着手

---

## ディレクトリ構成（新規作成ファイル）

```
skills/tax-collect/sites/
├── mufg-esmart/
│   ├── site.json
│   └── collect.py
├── tsumiki/
│   ├── site.json
│   └── collect.py
├── daiwa-connect/
│   ├── site.json
│   └── collect.py
├── paypay/
│   ├── site.json
│   └── collect.py
├── nomura-mochikabu/
│   ├── site.json
│   └── collect.py
├── hifumi/
│   ├── site.json
│   └── collect.py
└── sawakami/
    ├── site.json
    └── collect.py
```

site.json フォーマット（SBI準拠）:
```json
{
  "name": "野村證券持株会",
  "code": "nomura-mochikabu",
  "has_xml": false,
  "target_year": 2025,
  "output_dir": "data/income/securities/nomura-mochikabu/2025/raw/",
  "documents": [
    { "type": "特定口座年間取引報告書" }
  ]
}
```
