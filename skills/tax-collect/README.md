# tax-collect

証券会社・FX・クラウドファンディング等から確定申告用の年間取引報告書を自動収集する。

## 対応サービス

`registry.json` 参照。現在15社対応（証券14社 + webull Android）。

## 一括実行

```bash
# 全社（未収集のみ・webull は自動スキップ）
python skills/tax-collect/run.py --year <YEAR>

# 収集済みでも再実行
python skills/tax-collect/run.py --year <YEAR> --force

# 指定社のみ
python skills/tax-collect/run.py --year <YEAR> --sites sbi rakuten nomura

# 1社エラーで即停止
python skills/tax-collect/run.py --year <YEAR> --fail-fast
```

収集済み判定: `data/incomes/securities/<code>/<YEAR>/nenkantorihikihokokusho.json` の存在。

## 個別実行

```bash
python skills/tax-collect/sites/<code>/collect.py --year <YEAR>
```

## webull（Android）

```bash
python skills/tax-collect/sites/webull/collect.py --year <YEAR>
```

前提: ADB 接続済み（USB接続・USBデバッグ有効）

## 出力先

`data/incomes/securities/<code>/<YEAR>/`
