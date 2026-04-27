# #51 expense-collect に nomura (野村證券 取引履歴) 追加

## 対象 issue

[#51](https://github.com/genba-neko/agent-skills-money-ops/issues/51)

---

## 背景

expense-collect は現在 SBI のみ。野村證券の取引/注文履歴 CSV 収集を追加。
recorder データ (`output/recorder/nomura/20260427_100250/`) ベース。

---

## サイト分析（recorder トレース）

### URL 遷移

1. `rmfIndexWebAction.do` (ログイン)
2. `rmfCmnEtcInvTopAction.do` (ダッシュボード)
3. `rmfAstTrhTrhLstInitAction.do` (取引/注文履歴 初期画面)
4. `rmfAstTrhTrhLstAction.do` (照会結果)
5. CSV download → `rmfCmnCauSysLgoAction.do` (ログアウト)

### ログイン要素

- `input#branchNo` (branchNo) — 店番
- `input#accountNo` (accountNo) — 口座番号
- `input#passwd1` (gnziLoginPswd) — パスワード
- `button[text=ログイン][_ActionID]` — submit

### 期間指定 select

- 開始: `select#aselYear` (knskYFrom) / `select#aselMonth` (knskMFrom) / `select#aselDay` (knskDFrom)
- 終了: `select#bselYear` (knskYTo) / `select#bselMonth` (knskMTo) / `select#bselDay` (knskDTo)

**注意**: recorder では Year select は未操作 (User が当年デフォルトで実行)。
実装では target_year で aselYear/bselYear を明示 select 必要。

### 照会・ダウンロード

- `button[text=照会][_ActionID]` → form submit → rmfAstTrhTrhLstAction.do
- 結果画面で `a[text=CSVダウンロード]` が visible になるまで wait
- `a[text=CSVダウンロード]` click → `New_file.csv` ダウンロード

### 既ログイン検出

login_url 自体が `hometrade.nomura.co.jp/web/rmfIndexWebAction.do` で `skip_url_contains: hometrade.nomura.co.jp` だと誤発火する。
**`input#passwd1` 要素の有無で判定**:
- passwd1 が visible = 未ログイン → 手動ログイン待ち
- passwd1 が不存在 or 不可視 = ログイン済み → skip

### ナビゲーション経路

recorder ではダッシュボード経由「資産状況/履歴」→「取引/注文履歴」 nav click。
**実装は history_url (`rmfAstTrhTrhLstInitAction.do`) 直接 goto で試行**。
- 直接 goto OK ならそのまま
- ダメなら nav click 経由実装に切替

### 不要な操作 (recorder には記録だが実装不要)

- ダッシュボード「お預り資産状況閉じる」 click (副次的 UI 操作)
- 末尾の「ログアウト」 click (CSV取得後の片付け、自動 close で代替)

---

## 実装

### `skills/expense-collect/sites/nomura/site.json`

```json
{
  "name": "野村證券（取引履歴）",
  "code": "nomura",
  "target_year": 2025,
  "output_dir": "data/expenses/securities/nomura/{year}/raw/",
  "documents": [{ "type": "取引履歴" }],
  "login_url": "https://hometrade.nomura.co.jp/web/rmfIndexWebAction.do",
  "history_url": "https://hometrade.nomura.co.jp/web/rmfAstTrhTrhLstInitAction.do",
  "converter_type": "csv"
}
```

### `skills/expense-collect/sites/nomura/collect.py`

`SBIExpenseCollector` を参考に:
- `_wait_for_login(page)`:
  - login_url goto
  - `input#passwd1` 要素 visible 判定で未ログイン検出（URL ベースは誤発火するため不可）
  - 未ログイン → 手動ログイン完了まで 300 秒待機 (passwd1 不可視化を待つ)
  - ログイン済み → skip
- `_navigate_to_history(page)`: history_url (`rmfAstTrhTrhLstInitAction.do`) 直接遷移
- `_set_search_conditions(page, year)`:
  - aselYear/aselMonth/aselDay = year/01/01
  - bselYear/bselMonth/bselDay = year/12/31
  - `select_option(value=...)` で設定
- `_submit_and_download(page)`:
  - 「照会」 button click → 結果ページ遷移待機
  - 「CSVダウンロード」 link visible 待機 (timeout 30s)
  - link click → `expect_download` で受信
  - suggested_filename (New_file.csv) で `data/expenses/securities/nomura/<year>/raw/` 保存
  - 当年実行時に未来日エラー出るか実機検証 → 必要ならフォールバック追加

### `skills/expense-collect/registry.json` 追加

```json
{
  "code": "nomura",
  "name": "野村證券（取引履歴）",
  "category": "securities",
  "document_type": "取引履歴",
  "site_url": "https://www.nomura.co.jp/",
  "login_url": "https://hometrade.nomura.co.jp/web/rmfIndexWebAction.do",
  "history_url": "https://hometrade.nomura.co.jp/web/rmfAstTrhTrhLstInitAction.do",
  "collection": "auto"
}
```

---

## 実装タスク

- [x] `skills/expense-collect/sites/nomura/site.json` 作成
- [x] `skills/expense-collect/sites/nomura/collect.py` 作成
- [x] `skills/expense-collect/registry.json` に nomura entry 追加
- [x] 実機収集テスト → `data/expenses/securities/nomura/2025/raw/New_file.csv` 保存 OK
- [x] PR 作成・マージ

---

## 注意事項

- ログイン情報 (店番/口座番号/パスワード) はハードコード禁止 → 手動入力 or persistent profile cookie 利用
- 期間 select は `aselYear`/`bselYear` を target_year で **必ず明示設定** (recorder には記録なし)
- ファイル名は `New_file.csv` のまま suggested で保存 OK (年フォルダで自動分離)
- 当年実行時の挙動は実機検証 (未来日拒否なら SBI 同様 today fallback 追加)
- ナビゲーション経路は history_url 直接 goto で試行、ダメなら nav click 経由
