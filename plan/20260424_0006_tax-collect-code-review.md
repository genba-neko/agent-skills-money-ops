# tax-collect 全社コードレビュー 対応プラン [完了 PR#37 2026-04-26]

作成: 2026-04-24  
レビュー: Claude Opus（全15社 collect.py + BaseCollector 精査）  
前提: 動作確認済みコード。順次実装のため後発機能が古い社に未反映。

---

## BUG — 即対処

### B-1: monex dead code 削除
- ファイル: `skills/tax-collect/sites/monex/collect.py`
- 問題: `_download_pdf_via_route` が `return` 後に `captured` 未定義変数参照ブロックが残存
- 修正: 到達不能ブロックを削除

### B-2: webull 個人パスハードコード除去
- ファイル: `skills/tax-collect/sites/webull/collect.py`
- 問題: `_ADB_FALLBACK` に `C:\Users\g\AppData\...` ハードコード
- 修正: 環境変数 `ADB_PATH` から読み込む。未設定時はエラーメッセージで終了

### B-3: gmo-click expect_popup タイムアウトリスク
- ファイル: `skills/tax-collect/sites/gmo-click/collect.py`
- 問題: `with expect_popup():` 内で `input()` 待機 → 30秒デフォルトタイムアウトで死ぬ
- 修正: `input()` を `with` 外（popup open前）に移動 or `expect_popup(timeout=0)` 指定

### B-4: download failure 未検証（全社）
- 対象: sbi / rakuten / nomura / monex / matsui / gmo-click / smbcnikko（sawakami は対応済み）
- 問題: `save_as()` 成功 = 正常保存とみなし、0バイトや失敗を検知しない
- 修正: `download.failure()` チェック + PDF は `%PDF` マジックバイト確認を `BaseCollector` 共通ヘルパに追加

---

## MISSING — 機能非対称修正

### M-1: storage_state 保存（rakuten / nomura / smbcnikko）
- 問題: session cookie を保存しないため re-login 時に 2FA が毎回必要
- 修正: SBI 実装と同様に `_wait_for_login` 末尾で `storage_state` 保存を追加

### M-2: cookie 空時の保存スキップを BaseCollector に昇格
- 問題: mufg-esmart / sawakami だけガード有り。他社は空 storage_state で既存ファイルを破壊リスク
- 修正: `BaseCollector._save_session_state(page)` ヘルパを追加。cookie 0件時は保存スキップ。各社から呼ぶ

### M-3: `_is_logged_in` 自動スキップ（sbi / rakuten / nomura / monex / matsui / gmo-click / smbcnikko / hifumi）
- 問題: セッションが生きていても login 待ち `input()` が毎回発生
- 修正: 各社の `_wait_for_login` に「URL/要素で判定 → 既にログイン済みならスキップ」ロジックを追加（各社のトップ画面 URL or ログイン後に現れる要素で判定）

### M-4: webull に log_result を追加
- 問題: `BaseCollector` 未継承のため log_result が呼ばれずランナー統合不可
- 修正: 最低限 `BaseCollector` を継承する（adb ベースの処理は維持）。または `log_result` 相当を独自実装してインターフェース合わせ

### M-5: dlog/save_html を sbi / rakuten / matsui / gmo-click に追加
- 問題: 後発社だけデバッグログ対応。古い4社はデバッグ不能
- 修正: `dlog` / `save_html` 呼び出しを主要ステップに追加

---

## REFACTOR — 共通化

### R-1: `_wait()` を BaseCollector または utils に共通化
- 問題: `time.sleep(random.uniform(lo, hi))` が15ファイルにコピー
- 修正: `BaseCollector._wait(lo, hi)` or `money_ops.utils.wait(lo, hi)` に移動。各社の `_wait =` 削除

### R-2: `_RE_FILENAME` / `_extract_filename()` を utils に共通化
- 問題: `re.compile(r'filename[^;=\n]*=...')` が9社にコピー
- 修正: `money_ops.utils.http.extract_filename(response, fallback)` ヘルパに抽出

### R-3: e-shishobako PDF 捕捉ヘルパ抽出 [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 対象: sbi / gmo-click / nomura / hifumi（同一の DPAW010501020 route パターン）
- 修正: `money_ops.collector.eshishobako.capture_pdf(scope, fallback_name)` に共通化

### R-4: `_convert_to_json` + `_write_report_json` を BaseCollector に [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 問題: JSON書き出しボイラープレートが全社コピー
- 修正: `BaseCollector._write_report_json(data: dict)` を追加。各社は data を渡すだけ

### R-5: `collect()` スケルトンを Template Method 化 [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 問題: `try/except KeyboardInterrupt/Exception/finally close_browser` が全社コピー
- 修正: `BaseCollector.run()` にスケルトン実装。各社は `_collect_core()` のみ実装

### R-6: `__init__` の year / output_dir 構築を BaseCollector に移動 [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 問題: `self.config["target_year"] = year` / `output_dir = f"data/.../code/year/raw/"` が全社コピー
- 修正: `BaseCollector.__init__(site_json, year=None)` に `year` パラメータを追加。config mutation も廃止

---

## DESIGN — 設計改善（中長期）

### D-1: `sys.path.insert` を `pip install -e .` に統一 [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 問題: `Path(__file__).parents[4]` の深さ依存でディレクトリ移動で壊れる
- 修正: 開発環境セットアップドキュメントに `pip install -e .` を明記し、path 注入を削除

### D-2: `site.json` に login_url / converter_type を集約 [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 問題: `_LOGIN_URL` 等の定数がコードにハードコード。URL変更時にコード修正が必要
- 修正: `site.json` に `login_url`, `converter_type: "teg204_xml" | "pdf_llm"` を追加。BaseCollector が dispatch

### D-3: `input()` を PromptStrategy に抽象化（並列化の布石） [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 問題: `input()` がコード深部に散在。CLAUDE.md 要件の並列収集 Subagents 対応不可
- 修正: `PromptStrategy` 抽象（InteractivePrompt / EnvPrompt）を設計。ランナーから注入

### D-4: `HEADLESS` / `DEBUG` を CLI 引数化 [完了 branch:feature/34_tax-collect-code-review 2026-04-24]
- 問題: 全社共通グローバルフラグで社別制御不可
- 修正: `--headless` / `--debug` を argparse に追加し環境変数より優先

### D-5: `prompt()` / `input()` を `page.wait_for_url()` / `wait_for_event()` に置換（全社）
- 問題: `input()` が Bash ツール経由で EOF → Claude Codeスキルからの実行が不可能
- 根本解決: Enter待ちをやめ、ブラウザ状態（URL・要素・イベント）を自身で検出する
  - ログイン待ち → `page.wait_for_url(dashboard_pattern, timeout=300_000)`
  - 2FA後のポップアップ待ち → `session.wait_for_event("popup", timeout=300_000)`
  - OTP入力 → ユーザーがブラウザ直接入力・送信 → `page.wait_for_url()` で継続検出（スクリプトは fill/click 不要）
- GMO-click で動作確認済み（2026-04-24）: signal ファイル不要・チャット完結・ターミナル実行と共存

#### 全23箇所の分類（調査済み）

**カテゴリA: ログイン・ダッシュボード到達待ち（13箇所）→ `wait_for_url`**
- gmo-click, hifumi, matsui, monex, nomura, nomura-mochikabu, rakuten, sbi, smbcnikko, tsumiki, sawakami, paypay, webull(別途)

**カテゴリB: OTP/認証コード（5箇所）→ ユーザーがブラウザ直接入力+送信 → `wait_for_url`**
- daiwa-connect:84, mufg-esmart:121, paypay:103, sawakami:108, tsumiki:120
- スクリプト側の `page.fill(code)` + `click()` を削除。ブラウザで完結させる。

**カテゴリC: 中間フロー確認（5箇所）→ `wait_for_url` or `wait_for_selector` or `wait_for_event`**
- daiwa-connect:90, mufg-esmart:131/141, nomura:70, gmo-click:74（実装済み）

**webull**: Android/ADB のため別途検討

---

## 実装優先度

| Pri | Issue 候補 | 工数感 |
|-----|-----------|--------|
| **High** | B-1: monex dead code | 小 |
| **High** | B-2: webull ADB パスハードコード | 小 |
| **High** | B-3: gmo-click expect_popup | 小 |
| **High** | B-4: download failure 検証 + BaseCollector ヘルパ | 中 |
| **High** | M-2: cookie 空保護を BaseCollector に昇格 | 小 |
| **High** | M-4: webull log_result | 小 |
| Mid | R-1〜R-6: 共通化 | 中〜大 |
| Mid | M-1: storage_state（rakuten/nomura/smbcnikko） | 小 |
| Mid | M-3: `_is_logged_in` 追加 | 中（社ごと） |
| Mid | M-5: dlog 追加（古い4社） | 小 |
| Low | D-1〜D-4: 設計改善 | 大 |

---

## 関連ファイル

- `src/money_ops/collector/base.py` — BaseCollector
- `skills/tax-collect/sites/*/collect.py` — 各社スクリプト
- `skills/tax-collect/registry.json` — 会社定義
- `skills/tax-collect/run.py` — 一括実行ランナー
