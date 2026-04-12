# #9 XMLあり各社 Playwright収集スクリプト 実装プラン

## 対象 issue

[#9](https://github.com/genba-neko/agent-skills-money-ops/issues/9) XMLあり各社 Playwright収集スクリプト（楽天証券以外）

---

## 背景・前提知識（操作記録から得た知見）

### ① PDFダウンロード問題

楽天証券では Chrome PDF ビューアが先にインターセプトするため `context.route()` でバイトを捕捉する特殊実装が必要だった。  
他の XMLあり各社は **iframe 内に PDF ビューアを埋め込み + ダウンロードボタン形式** であり、`expect_download()` でキャプチャ可能。

| 会社 | PDF取得方式 |
|---|---|
| 楽天証券（#8 実装済み） | `context.route()` でバイト捕捉 |
| SBI証券 | ポップアップ内 iframe（ランダム name属性） + ダウンロードボタン → `expect_download()` |
| 野村證券 | ポップアップ内 iframe（ランダム name属性） + ダウンロードボタン → `expect_download()` |
| マネックス証券 | ダブルiframe（`frame[name="PDF"]` 内にさらに iframe）+ ダウンロードボタン → `expect_download()` |
| 松井証券 | frameset構成（`frame[name="pdfout"]` 内に iframe）+ ダウンロードボタン → `expect_download()` |
| GMOクリック証券 | ポップアップ内 iframe（ランダム name属性）+ ダウンロードボタン → `expect_download()` |
| SMBC日興証券 | ポップアップ内 iframe（ランダム name属性）+ ダウンロードボタン → `expect_download()` |

> iframe name属性がランダム値のため `iframe[name="..."]` 直接指定は不可。  
> `page.frame_locator("iframe")` + `get_by_role("button", name="ダウンロード")` で探索する。

---

### ② 年間取引報告書の年度表記

年間取引報告書は **対象年度末（12月下旬）〜翌年1月初旬** に発行される。  
発行が12月になる場合は発行年 = `target_year`、1月の場合は `target_year + 1` となり、**`issue_year = target_year + 1` の固定算出は不可**。

**対策**: 発行年月で絞り込む会社（SBI, Monex, Matsui, GMO）については、発行年月として想定される2パターン — **`{target_year}/12`（12月末発行）** と **`{target_year+1}/01`（翌年1月発行）** — の両方でロケーターを試み、ヒットした方を使う。  
年のみで絞り込むと前年度分の書類にもヒットするため、必ず年月まで含めること。  
発行日ではなく対象年度で絞り込める会社（野村）や書類種別チェックボックス絞り込み（SMBC日興）はこの問題に影響されない。

| 会社 | 一覧上の表示形式 | ロケーター戦略 |
|---|---|---|
| SBI証券 | `"2026/01/13"` ボタン（発行日）→ 書類名ボタン | `f"{target_year}/12"` または `f"{target_year+1}/01"` を含むボタン（両方試みる） |
| 野村證券 | `"2026/01/07 特定口座年間取引報告書 2025"` | ボタン名に `str(target_year)` を含む行（発行年に依存しない） |
| マネックス証券 | `"特定口座年間取引報告書2026年01月06日 XML"` | `f"{target_year}年12月"` または `f"{target_year+1}年01月"` を含むリンク（両方試みる） |
| 松井証券 | `"特定口座年間取引報告書（XMLファイル）2026年01月"` | `f"{target_year}年12月"` または `f"{target_year+1}年01月"` を含むリンク（両方試みる） |
| GMOクリック証券 | `"2026/01/08 特定口座年間取引報告書 GMO"` | `f"{target_year}/12"` または `f"{target_year+1}/01"` を含むボタン（両方試みる） |
| SMBC日興証券 | 書類種別チェックボックス絞り込み後、行リスト先頭 | `first` を使用（日付順ソートを前提、発行年に依存しない） |

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
| 絞り込み | `str(target_year)` を含むボタンをクリック |
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
| PDF取得 | `"..."` （XML なし） リンク → ポップアップ → ダブル `iframe` 内ダウンロードボタン → `expect_download()` |
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
| ログイン | ログインページを開き人間が手動でログイン・ポップアップ処理・トップ画面到達後 Enter |
| ナビゲーション | ポップアップ → キーワード検索 `"特定口座年間取引報告書"` → `f"{issue_year}/"` ボタン |
| XML取得 | `"特定口座年間取引報告書（xmlデータ）"` ボタン → `expect_download()` |
| PDF取得 | `"特定口座年間取引報告書（PDFファイル）"` ボタン → ポップアップ → `iframe` 内ダウンロードボタン → `expect_download()` |
| skip条件 | `f"{issue_year}/"` ボタンが存在しない |

### SMBC日興証券（smbcnikko）

| 項目 | 内容 |
|---|---|
| ログイン | ログインページを開き人間が手動でログイン・ポップアップ処理・トップ画面到達後 Enter |
| ナビゲーション | 各種お手続き → 電子交付サービス → 電子交付履歴 → 書類種別チェックボックス絞り込み → 検索 |
| 絞り込み | `"特定口座年間取引報告書"` チェックボックス → 検索後、行リスト先頭（`.first`） |
| XML取得 | 行の XML リンク → 取引パスワード認証ポップアップ → `expect_download()` |
| PDF取得 | 行の PDF リンク → ポップアップ → `iframe` 内ダウンロードボタン → `expect_download()` |
| skip条件 | 検索結果に行が存在しない |

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
