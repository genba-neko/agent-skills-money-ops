---
name: expense-collect
description: >
  銀行・証券・クレカ等から入出金明細（CSV）を自動収集するスキル。
  「expense-collect実行して」「入出金明細収集して」「家計データ集めて」で起動。
---

## 呼び出し時の動作

このスキルが呼ばれたら以下を順番に実行する。

### 1. パラメータ確認

ユーザーに以下を確認する（会話から読み取れる場合は省略）:

- **対象年（暦年）**: 未指定なら当年をデフォルトとして提案
  - 過去年: 該当年 1/1〜12/31
  - 当年: 該当年 1/1〜今日（サイトが未来日拒否時にフォールバック）
  - 未来年: エラー
- **対象会社**: 未指定なら「全社（未収集のみ）」で実行
- **強制再収集**: 収集済みの会社も再実行するか（デフォルト: しない）

### 2. 実行

確認後、以下を実行する:

```bash
python skills/expense-collect/run.py --year <YEAR> [オプション]
```

オプション:
- `--sites <code> ...` — 特定社のみ（例: `sbi`）
- `--force` — 収集済みでも再実行
- `--fail-fast` — 1社エラーで即停止

### 3. 結果報告

実行後、サマリー（OK / ERROR / DONE / SKIP）をユーザーに報告する。
ERROR が出た場合は内容を確認してユーザーに伝える。

---

## 対応会社コード一覧

`skills/expense-collect/registry.json` を参照。

## 収集済み判定

`data/expense/<code>/<year>/raw/` 配下に CSV ファイルが 1 つ以上存在で収集済みと判断。

## 前提条件

- `money_ops` パッケージがインストール済みであること（`pip install -e .` を実行済み）
- 各 `collect.py` は `money_ops` がインストールされた環境の Python で実行する必要がある
- `run.py` は `sys.executable` で子プロセスを起動するため環境は自動引き継ぎされる

## 注意事項

- ブラウザが起動したらユーザーが手動でログイン・2FA処理を行う
- 2FA・OTP・CAPTCHA が出たらユーザーに手動介入を依頼する
- tax-collect と同じ persistent profile（`~/.money-ops-browser/<code>/`）を共有
  - tax-collect 完了後の実行を推奨（cookie 競合回避）
