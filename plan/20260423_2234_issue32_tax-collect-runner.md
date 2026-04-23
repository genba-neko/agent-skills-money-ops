# tax-collect 一括実行ランナー [完了 PR#35 2026-04-24]

## 目的

15社の収集スクリプトを個別実行から一元管理する CLI ランナー実装。

## 実装対象

`skills/tax-collect/run.py`（新規）

## 実行イメージ

```bash
# 全社実行
python skills/tax-collect/run.py --year 2025

# 指定社のみ
python skills/tax-collect/run.py --year 2025 --sites sbi rakuten nomura

# manual除外（Playwright自動のみ）
python skills/tax-collect/run.py --year 2025 --skip-manual
```

## 設計

### 処理フロー

1. `registry.json` を読み込み対象社リスト構築
2. `--sites` 指定あり → 該当社のみ、なし → 全社
3. `collection: manual` の社（webull）はスキップ or 警告表示
4. 各社 `sites/<code>/collect.py` を **subprocess** で順次起動
   - サブプロセス方式: 各スクリプトが `sys.path` 操作・argparse を持つため import 方式は衝突リスクあり
5. 各社実行後に成功/失敗/スキップを集計
6. 全社完了後サマリー表示

### subprocess 起動方式

```
python skills/tax-collect/sites/<code>/collect.py --year YYYY
```

- `stdin` を継承（人間の手動 Enter 入力を受け取るため）
- `capture_output=False`（各社の print をそのままターミナルへ流す）
- タイムアウトなし（人間待ち操作があるため）

### manual 社の扱い

- `collection: manual` → 実行前に `[SKIP] webull: 手動収集対象` を表示してスキップ
- `--include-manual` フラグで明示的に含められる（将来拡張）

### エラー処理

- 1社で例外 or returncode != 0 でも次社へ継続（`--fail-fast` で即停止オプション）
- 最後にサマリー:

```
=== 収集結果 ===
  OK   : sbi, rakuten, nomura
  ERROR: matsui (returncode=1)
  SKIP : webull (manual)
```

### CLI 引数

| 引数 | デフォルト | 説明 |
|------|-----------|------|
| `--year` | 前年 | 対象年度 |
| `--sites` | 全社 | 絞り込み（複数指定可） |
| `--skip-manual` | False | manual 社を除外（デフォルトでも除外） |
| `--fail-fast` | False | 1社エラーで即停止 |

## ファイル構成

```
skills/tax-collect/
├── run.py          # ← 新規追加
├── registry.json
├── SKILL.md        # ← 使い方追記
└── sites/
    └── <code>/collect.py
```

## 非実装（スコープ外）

- 並列実行（Playwright ウィンドウが複数同時起動して混乱する可能性）
- webull の uiautomator2 自動起動統合

## 関連

- registry.json: `skills/tax-collect/registry.json`
- 各社スクリプト: `skills/tax-collect/sites/*/collect.py`
