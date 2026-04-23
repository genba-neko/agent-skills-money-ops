---
name: tax-collect
description: >
  証券会社・FX・クラウドファンディング等から年間取引報告書を自動収集するスキル。
  「tax-collect実行して」「年間報告書収集して」「確定申告データ集めて」で起動。
---

## 呼び出し時の動作

このスキルが呼ばれたら以下を順番に実行する。

### 1. パラメータ確認

ユーザーに以下を確認する（会話から読み取れる場合は省略）:

- **対象年度**: 未指定なら前年をデフォルトとして提案
- **対象会社**: 未指定なら「全社（未収集のみ）」で実行
- **強制再収集**: 収集済みの会社も再実行するか（デフォルト: しない）

### 2. 実行

確認後、以下を実行する:

```bash
python skills/tax-collect/run.py --year <YEAR> [オプション]
```

オプション:
- `--sites <code> ...` — 特定社のみ（例: `sbi rakuten`）
- `--force` — 収集済みでも再実行
- `--fail-fast` — 1社エラーで即停止

### 3. 結果報告

実行後、サマリー（OK / ERROR / DONE / SKIP）をユーザーに報告する。
ERRORが出た場合は内容を確認してユーザーに伝える。

## 対応会社コード一覧

`skills/tax-collect/registry.json` を参照。
`collection: android` の会社（webull）は実行前にUSB接続・USBデバッグ・アプリログインをユーザーに促し、確認後に自動実行する。

## 収集済み判定

`data/income/securities/<code>/<year>/nenkantorihikihokokusho.json` の存在で判断。

## 注意事項

- ブラウザが起動したらユーザーが手動でログイン・2FA処理を行う
- 2FA・CAPTCHA が出たらユーザーに手動介入を依頼する
- webull は Android/ADB 接続が前提（事前確認を促す）
