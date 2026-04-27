# #56 rakuten collector に配当金履歴 CSV 採取追加

## 対象 issue

[#56](https://github.com/genba-neko/agent-skills-money-ops/issues/56)

---

## 背景

PR #54 で採取した入出金履歴 CSV (Withdrawallist) には配当金が含まれず（楽天銀行 ↔ 証券口座間の資金移動と株購入用入金のみ）、配当金集計のため別画面採取が必要。

recorder データ `output/recorder/rakuten/20260427_152252/` で配当・分配金画面のフロー確認済。

---

## サイト分析（recorder 確認）

### URL

- 配当・分配金画面: `https://member.rakuten-sec.co.jp/app/ass_dividend_history.do?eventType=init&gmn=S&smn=06&lmn=01&fmn=01`
- CSV download: 同 URL の `?eventType=csv`
- ファイル名: `dividendlist_<YYYYMMDD>.csv`

### Nav 経路

1. ログイン → home.do (PR #54 で実装済の流れ流用)
2. 「口座管理・入出金など」 button
3. 「配当・分配金」 link
4. ass_dividend_history.do 到達

### 期間 select

- 開始: `select#yearFrom`, `select#monthFrom`, `select#dayFrom`
- 終了: `select#yearTo`, `select#monthTo`, `select#dayTo`
- target_year で 1/1〜12/31 設定

### CSV エクスポート

recorder の click 操作不明（DL イベントのみ取得）。
URL パターンから推測: `img.roll` 等の link click → `?eventType=csv` への navigation で download。
入出金履歴と同じ仕組みと推測。

---

## 実装方針

`RakutenExpenseCollector._collect_core` を拡張:

```python
def _collect_core(self, page) -> None:
    self._wait_for_login(page)
    paths = []

    # 1. 入出金履歴 (既存)
    self._navigate_to_history(page)  # マイメニュー → 入出金履歴
    p1 = self._submit_and_download(page)
    if p1: paths.append(p1)

    # 2. 配当金履歴 (追加)
    self._navigate_to_dividend(page)  # マイメニュー → 配当・分配金
    self._set_dividend_period(page)
    p2 = self._submit_and_download_dividend(page)
    if p2: paths.append(p2)

    if not paths:
        self.log_result("error", [], "両 CSV 取得失敗")
    else:
        self.log_result("success", paths)
```

### 新メソッド

- `_navigate_to_dividend(page)`: マイメニュー → 「配当・分配金」 link click
- `_set_dividend_period(page)`: yearFrom/monthFrom/dayFrom + yearTo/monthTo/dayTo 6 select 設定
- `_submit_and_download_dividend(page)`: CSV エクスポート link click → `dividendlist_*.csv` 保存

### 出力先

`data/expenses/securities/rakuten/<year>/raw/` 配下に:
- `Withdrawallist_<date>.csv` (入出金、既存)
- `dividendlist_<date>.csv` (配当金、追加)

---

## 実装タスク

- [ ] `skills/expense-collect/sites/rakuten/collect.py` 拡張
  - `_navigate_to_dividend` 追加
  - `_set_dividend_period` 追加 (期間 select 6個)
  - `_submit_and_download_dividend` 追加 (CSV link selector は HAR/recorder 再分析で確定)
  - `_collect_core` で 2段階採取に変更
- [ ] 実機テスト
  - `python skills/expense-collect/run.py --year 2025 --sites rakuten --force`
  - 両 CSV 保存確認: `Withdrawallist_*.csv` + `dividendlist_*.csv`
- [ ] 配当金 CSV の中身サンプリング確認 (列構成、列名、件数)
- [ ] PR 作成・マージ

---

## 注意事項

- 入出金履歴側 (PR #54 実装) は変更せず、配当金処理を後続で追加
- マイメニューを 2 回開くため _wait 適切に挟む
- 配当金画面 form の selector / CSV link の selector は HAR で確認 (recorder の click 記録なし)
- ログイン状態は 1 回で 2 画面分カバー (collector 1 セッション)

---

## 関連

- recorder: `output/recorder/rakuten/20260427_152252/`
- 既存実装: `skills/expense-collect/sites/rakuten/collect.py` (PR #54 で導入)
- 後続: #55 共通フォーマット正規化（配当金 CSV あり前提で進めやすくなる）
