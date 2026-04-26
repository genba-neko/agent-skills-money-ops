# expense-collect

銀行・証券・クレカ等から入出金明細（CSV）を自動収集する。

## 対応サービス

`registry.json` 参照。

## 一括実行

```bash
# 全社（未収集のみ）
python skills/expense-collect/run.py --year <YEAR>

# 収集済みでも再実行
python skills/expense-collect/run.py --year <YEAR> --force

# 指定社のみ
python skills/expense-collect/run.py --year <YEAR> --sites sbi

# 1社エラーで即停止
python skills/expense-collect/run.py --year <YEAR> --fail-fast
```

収集済み判定: `data/expenses/<code>/<YEAR>/raw/` に CSV ファイルが 1 つ以上存在。

## 個別実行

```bash
python skills/expense-collect/sites/<code>/collect.py --year <YEAR>
```

## 期間指定

`--year <YEAR>`（暦年）の取扱:
- 過去年: `YYYY/01/01 〜 YYYY/12/31`
- 当年: `YYYY/01/01 〜 YYYY/12/31`（サイトが未来日拒否時は `YYYY/01/01 〜 今日` にフォールバック）
- 未来年: エラー

## tax-collect との関係

- 同じ persistent profile（`~/.money-ops-browser/<code>/`）を共有
- tax-collect 完了後の実行を推奨（cookie 競合回避）
