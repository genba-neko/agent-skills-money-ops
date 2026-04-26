# #41 expense-collect スキル新設 + SBI 入出金明細 CSV 自動収集

## 対象 issue

[#41](https://github.com/genba-neko/agent-skills-money-ops/issues/41)

---

## 背景

- tax-collect = 確定申告用の年間取引報告書（PDF）取得
- 日常家計管理・経費把握には **入出金明細** が必要
- 新スキル `expense-collect` を新設し SBI から開始
- recorder で SBI 入出金明細 CSV ダウンロードフローを採取済み

---

## 操作データ（recorder 出力）

`output/recorder/sbi/20260427_005054/`

- `summary.md` — URL 推移・ユーザー操作 26 件記録
- `events.jsonl` — 全イベント時系列（user_click / user_input / user_change 含む）
- `network.har` — リクエスト・レスポンス
- `trace.zip` — Playwright Trace
- `dom_*.html` — milestone 地点 DOM

---

## フロー（実測）

```
1. www.sbisec.co.jp/ETGate/ （ログイン画面）
2. 「ログイン」 link click → login.sbisec.co.jp/login/entry
3. username 入力 + password 入力 → 「ログイン」 button click
4. POST login.sbisec.co.jp/idpw/auth
5. login.sbisec.co.jp/otp/entry → 「メール送信」 button
6. login.sbisec.co.jp/otp/confirm → authCode 表示確認
7. authCheckBox check + 「デバイスを登録する」 button click
8. login.sbisec.co.jp/otp/complete → /sso/request → site2.sbisec.co.jp/ETGate/ （ダッシュボード）
9. 「入出金」 メニュー click → member.c.sbisec.co.jp/banking/yen/deposit
10. 「入出金明細」 link click → member.c.sbisec.co.jp/banking/yen/detail-history
11. 期間チェックボックス click + 開始日「YYYY/01/01」 入力
12. 「照会」 button click
13. 「CSVダウンロード」 button click → DetailInquiry_YYYYMMDDHHMMSS.csv ダウンロード
```

---

## 実装方針

### スキル構成（tax-collect に準拠）

```
skills/expense-collect/
├── README.md                # スキル概要
├── SKILL.md                 # スキル仕様・使い方（Claude 起動用 frontmatter）
├── registry.json            # 対応サイト一覧
├── run.py                   # 一括実行ランナー
└── sites/
    └── sbi/
        ├── site.json
        └── collect.py
```

将来追加（このプランでは含まず）:
- `convert.py` / `convert_worker.py` — CSV→統一 JSON 変換
- `recorder.py` — tax-collect と共通化検討（src 配下移動 or symlink）

### 共通基盤

- `src/money_ops/collector/base.py` の **BaseCollector を再利用**
  - 既に persistent context・cookie 復元・session 保存・TRACE 機能完備
  - `_collect_core` を override して expense 用ロジック実装
  - 出力ディレクトリと収集ファイル種類のみ違う

- 必要なら `src/money_ops/collector/expense_base.py` で expense 専用拡張
  - CSV ダウンロード共通ヘルパ
  - 入出金 CSV のスキーマ統一（後述）

### 出力先

```
data/expense/<code>/<year>/raw/<original_filename>.csv
data/expense/<code>/<year>/transactions.json   # 統一スキーマ JSON
```

tax-collect が `data/income/securities/<code>/<year>/raw/` を使用しているので、
それと並列に `data/expense/<code>/<year>/raw/` 構造を採用。

### 統一スキーマ（後続）

各社 CSV はフォーマット異なる → 統一 JSON に変換。

```json
{
  "code": "sbi",
  "year": 2025,
  "transactions": [
    {
      "date": "2025-01-15",
      "amount": -1234,           // マイナス=出金、プラス=入金
      "balance": 100000,
      "description": "...",
      "category": "withdrawal"   // optional（自動分類）
    }
  ]
}
```

CSV→JSON 変換は別タスク（このプランには含めず最小実装で CSV 保存まで）。

### login_url・URL 戦略

- `site_url`: `https://www.sbisec.co.jp/`
- `login_url`: `https://www.sbisec.co.jp/ETGate/`（tax-collect の SBI と同じ）
- `dashboard_url`: `https://site2.sbisec.co.jp/ETGate/`
- `target_history_url`: `https://member.c.sbisec.co.jp/banking/yen/detail-history`（直接遷移可能なら最短経路）

### tax-collect SBI との profile 共有

- `~/.money-ops-browser/sbi/` を tax-collect SBI と共有（cookie / OTP デバイス登録 流用）
- ただし tax-collect は site2.sbisec.co.jp/ETGate/, expense-collect は member.c.sbisec.co.jp/banking/
  → 同セッション内で両方アクセス可能のはず（実装で確認）

検討事項: profile 名を別にして衝突回避するか、共有でいくか。
- 共有メリット: ログイン 1 回で済む
- 共有デメリット: 並列実行時 cookie 競合、片方の更新がもう片方に影響
- **推奨: 共有（家計管理とは tax-collect 終了後に実行する想定）**

### 期間指定（重要）

- CLI 引数: `--year YYYY`
- **過去年（YYYY < 今年）**: `YYYY/01/01 〜 YYYY/12/31`（年全体）
- **当年（YYYY == 今年）**:
  - 試行 1: `YYYY/01/01 〜 YYYY/12/31` を入力して「照会」
  - サイトが未来日拒否したら 試行 2: `YYYY/01/01 〜 今日` で再入力
  - 動作確認後どちらが正しいか確定

### 実装

```python
from datetime import date

def _build_date_range(target_year: int) -> tuple[str, str]:
    today = date.today()
    start = f"{target_year}/01/01"
    if target_year < today.year:
        end = f"{target_year}/12/31"
    elif target_year == today.year:
        # 試行 1: 12/31 まで指定。サイトが未来日エラーなら今日に切替
        end = f"{target_year}/12/31"  # 後段で照会失敗時 today.strftime("%Y/%m/%d") にフォールバック
    else:
        raise ValueError(f"未来年は指定不可: {target_year}")
    return start, end
```

照会失敗パターン（alert・error message）を検出してフォールバックする実装にする。

- recorder 確認: 開始日 `2026/01/01` 入力 → 終了日省略（デフォルト今日）
  - 実装上は終了日を明示指定したい（過去年との一貫性のため）

### 自動 vs 手動の境界

- ID/PW 入力: **手動**（環境変数 `SBI_USER` / `SBI_PASS` 対応も検討）
- OTP 認証: **手動**（メール OTP 確認・デバイス登録）
- それ以降の navigation・期間入力・CSV ダウンロード: **自動**

---

## 実装タスク

1. **基盤**
   - [ ] `skills/expense-collect/` ディレクトリ新設
   - [ ] `registry.json` 設計（tax-collect 形式に倣う）
   - [ ] `SKILL.md` スキル仕様記述
   - [ ] `run.py` 一括実行ランナー（tax-collect の run.py 流用）

2. **SBI サイト実装**
   - [ ] `sites/sbi/site.json` 作成
   - [ ] `sites/sbi/collect.py` 実装
     - ログイン待ち（ダッシュボード要素 visible 検出）
     - 入出金明細画面遷移
     - 期間入力（target_year/01/01）
     - 「照会」 click
     - 「CSVダウンロード」 button click → download 捕捉
     - CSV 保存（`data/expense/sbi/<year>/raw/`）

3. **動作確認**
   - [ ] 単体実行: `python skills/expense-collect/sites/sbi/collect.py --year 2025`
   - [ ] CSV ファイル取得確認
   - [ ] tax-collect SBI と profile 共有時の挙動確認（cookie 競合なし）

4. **将来タスク（このプランでは扱わない）**
   - CSV→統一 JSON 変換
   - 他サイト対応（楽天銀行、住信SBI、三菱UFJ 等）
   - 自動分類（カテゴリ推定）

---

## リスク

- **R-1**: BaseCollector が tax-collect 専用設計の場合、共通化が困難
  - 対策: 必要に応じて expense 専用基底クラス導入

- **R-2**: SBI の入出金明細画面 DOM が変更される可能性
  - 対策: recorder の user_ops データを基に実装、selector 変更に強いロケート（label/role）使用

- **R-3**: CSV のスキーマが将来変更される
  - 対策: 統一 JSON 化は別タスクで実装、生 CSV は raw/ に保管

---

## 参考

- recorder 出力: `output/recorder/sbi/20260427_005054/`
- tax-collect 実装: `skills/tax-collect/sites/sbi/collect.py`（profile 共有）
- BaseCollector: `src/money_ops/collector/base.py`
