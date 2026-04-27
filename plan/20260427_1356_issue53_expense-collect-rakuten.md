# #53 expense-collect に rakuten (楽天証券 入出金履歴) 追加

## 対象 issue

[#53](https://github.com/genba-neko/agent-skills-money-ops/issues/53)

---

## 背景

配当金入金の集計用に楽天証券の入出金履歴 CSV 採取を追加。
recorder データ `output/recorder/rakuten/20260427_134019/` ベース。

---

## サイト分析

### URL

- ログイン: `https://member.rakuten-sec.co.jp/app/MhLogin.do?login_type=1` （tax-collect/rakuten と統一）
- 入出金履歴: `https://member.rakuten-sec.co.jp/app/ass_money_trans_lst.do?eventType=init&gmn=S&smn=03&lmn=03&fmn=01`
  - 注意: BV_SessionID はセッションごとに変わる → query 部分のみ使用
- CSV download: 入出金履歴ページ内 `img.roll` (CSV エクスポート画像 link)

### CSV 仕様

- ファイル名: `Withdrawallist_<YYYYMMDD>.csv`
- 1 click で **全期間 1515 行**（ヘッダ + 全件）取得済確認
- ページネーション (12 ページ) は画面表示用、CSV エクスポートには反映されない

### ログイン

- tax-collect/rakuten/collect.py の `_wait_for_login` 流用
  - login_url を tax-collect 側と同じにすることで 1 ステップ短縮（`www.rakuten-sec.co.jp/ITS/...` 経由不要）
- URL ベース判定: `member.rakuten-sec.co.jp/app/` 配下到達 + `Login` を含まない → skip
- 絵文字認証・パスキーは手動（300秒待機）

---

## 実装

### `skills/expense-collect/sites/rakuten/site.json`

```json
{
  "name": "楽天証券（入出金履歴）",
  "code": "rakuten",
  "target_year": 2025,
  "output_dir": "data/expenses/securities/rakuten/{year}/raw/",
  "documents": [{ "type": "入出金履歴" }],
  "login_url": "https://member.rakuten-sec.co.jp/app/MhLogin.do?login_type=1",
  "history_url": "https://member.rakuten-sec.co.jp/app/ass_money_trans_lst.do?eventType=init&gmn=S&smn=03&lmn=03&fmn=01",
  "converter_type": "csv"
}
```

### `skills/expense-collect/sites/rakuten/collect.py`

`SBIExpenseCollector` 構造踏襲、ログイン部分は tax-collect/rakuten 参考:
- `_wait_for_login(page)`: login_url goto → URL に member.rakuten-sec.co.jp/app/ 含み Login 含まなければ skip、なければ手動ログイン待ち（300秒）
- `_navigate_to_history(page)`: history_url 直接 goto
- `_submit_and_download(page)`: CSV エクスポート link click → expect_download → suggested_filename で保存
  - **selector 戦略**: 入出金履歴ページ内に img.roll が複数ある可能性
    - 第一候補: `form#AssMoneyTransLstForm img.roll`（form 内に限定）
    - フォールバック: `tbody > tr > td > div.mbody > a > img.roll` の `.first`
    - 実機検証で確定

### `skills/expense-collect/registry.json` 追加

```json
{
  "code": "rakuten",
  "name": "楽天証券（入出金履歴）",
  "category": "securities",
  "document_type": "入出金履歴",
  "site_url": "https://www.rakuten-sec.co.jp/",
  "login_url": "https://member.rakuten-sec.co.jp/app/MhLogin.do?login_type=1",
  "history_url": "https://member.rakuten-sec.co.jp/app/ass_money_trans_lst.do?eventType=init&gmn=S&smn=03&lmn=03&fmn=01",
  "collection": "auto"
}
```

---

## 実装タスク

- [x] `skills/expense-collect/sites/rakuten/site.json` 作成
- [x] `skills/expense-collect/sites/rakuten/collect.py` 作成
- [x] `skills/expense-collect/registry.json` に rakuten entry 追加
- [x] 実機収集テスト → `data/expenses/securities/rakuten/2025/raw/Withdrawallist_20260427.csv` (1515 行) 出力確認
- [x] PR 作成・マージ

## 実装中の修正履歴

1. login_url を `MhLogin.do?login_type=1` → `https://www.rakuten-sec.co.jp/` (top) に変更
   （直接 MhLogin.do は session 切れで session_error.html に redirect されるため）
2. ログイン状態判定 `_is_dashboard` を URL path ベースに変更
   （query の `login_type=1` を誤検出して dashboard 判定 False になる問題）
3. 履歴ページ遷移を nav click 経由に変更
   （直接 goto では BV_SessionID 不足で form 表示されない）
4. form selector を `form#AssMoneyTransLstForm` (id) → `form[name='AssMoneyTransLstForm']` に変更
   （HTML 実態は name 属性のみ、id なし。recorder の sel 表記 `form#...` は誤読しやすかった）
5. login タイムアウト 5分 → 10分に延長

---

## 注意事項

- target_year は CSV エクスポートに反映されない（全期間取得）→ 年フォルダ分離だが内容は全期間同じ
  - 後段の集計処理で year フィルタ必要
  - site.json target_year は管理用 (output_dir 用)
- 配当金集計は CSV 内の摘要行で抽出（後段処理、本タスクの責務外）
