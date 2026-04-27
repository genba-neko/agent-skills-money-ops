# #55 証券会社入出金明細CSVの共通フォーマット正規化

## 対象 issue

[#55](https://github.com/genba-neko/agent-skills-money-ops/issues/55)

---

## 背景

expense-collect で採取した各社入出金明細 CSV はフォーマット差異あり、年次集計・配当金抽出のため共通スキーマへ正規化が必要。

---

## サンプリング分析結果

### SBI (`DetailInquiry_*.csv`, UTF-8 BOM)

```
（先頭3行は見出し + メタ情報）
入出金日,取引,区分,摘要,出金額,入金額
"2025/12/30","出金","その他","投信るいとうお買付預り金振替","100000","0"
"2025/12/26","入金","その他","譲渡益税還付金","0","11438"
```

特徴:
- 5 列固定 (日付, 取引種別, 区分, 摘要, 出金額, 入金額)
- 出金/入金 別列で符号フリー
- 配当金は摘要文字列に「配当金」含む

### nomura (`New_file.csv`, UTF-8 BOM)

```
（先頭5行は見出し + メタ情報）
約定日,受渡日,商品,銘柄コード,銘柄名,摘要,取引区分,預り区分,発行通貨,数量,単価,受渡金額/決済損益,手数料（税込）,レート,決済通貨,売買損益（円）
"2025/12/09","...","株式","9023","東京地下鉄","","入金（配当金）","","","100","21","1674","","","",""
```

特徴:
- 16 列 (取引履歴詳細)
- 取引区分が明示 (`入金（配当金）` `現物売却` `出金（振込）` 等)
- 銘柄コード/銘柄名 別列
- 受渡金額が一列に集約 (符号は取引区分で推定)

### rakuten (`Withdrawallist_*.csv`, cp932)

```
（先頭3行は集計サマリ）
入出金日,入金額[¥],出金額[¥],内容,お取引区分
```

特徴:
- 5 列 (日付, 入金, 出金, 内容, 取引区分)
- encoding cp932 (Shift-JIS)
- 銘柄コード抽出は要調査 (内容文字列内?)

---

## 共通スキーマ

```python
@dataclass
class Transaction:
    date: str             # ISO 8601 "YYYY-MM-DD"
    amount_in: int        # 円, 入金 (none=0)
    amount_out: int       # 円, 出金 (none=0)
    description: str      # 摘要 + 銘柄名 等を結合
    category_raw: str     # 元CSVの取引区分そのまま
    category: str         # 正規化: dividend/sale/purchase/deposit/withdrawal/tax/other
    security_code: str | None  # 銘柄コード（あれば）
    security_name: str | None  # 銘柄名（あれば）
    raw: dict             # 元CSV row（key=ヘッダ列名）

@dataclass
class NormalizedReport:
    schema_version: str = "1.0"
    broker: str           # "sbi" | "nomura" | "rakuten"
    year: int
    source_file: str
    transactions: list[Transaction]
    summary: dict         # {"total_in", "total_out", "count"}
```

出力 JSON: `data/expenses/securities/<code>/<year>/normalized.json`

---

## カテゴリ正規化ルール

| category | パターン |
|----------|---------|
| `dividend` | 「配当金」「分配金」を摘要 or 取引区分に含む |
| `sale` | 「売却」「現物売却」を取引区分に含む |
| `purchase` | 「買付」「お買付」を取引区分 or 摘要に含む |
| `deposit` | 「入金」かつ dividend/sale でないもの (振替入金、銀行入金等) |
| `withdrawal` | 「出金」(振込/振替) |
| `tax` | 「税」「源泉徴収」を含む |
| `other` | 上記いずれにも該当しないもの |

優先順位: dividend > sale > purchase > tax > deposit/withdrawal > other

---

## 実装

### ファイル構成

```
src/money_ops/
└── normalizer/
    ├── __init__.py
    └── expense_csv.py    # Transaction / NormalizedReport dataclass + 共通ヘルパ + classify

skills/expense-collect/
├── parsers/
│   ├── __init__.py
│   ├── sbi.py            # SBI CSV → list[Transaction]
│   ├── nomura.py         # nomura CSV → list[Transaction]
│   └── rakuten.py        # rakuten CSV → list[Transaction]
└── normalize.py          # CLI: --year YYYY [--sites CODE]
```

### 各 parser インタフェース

```python
def parse(csv_path: Path, year: int) -> list[Transaction]:
    """CSV ファイルを読み、当該 year のトランザクション list を返す"""
```

### normalize.py 動作

1. registry.json から対象 account 取得
2. 各 code の `data/expenses/securities/<code>/<year>/raw/*.csv` を find
3. 該当 parser をディスパッチ → list[Transaction]
4. NormalizedReport 構築 → `data/expenses/securities/<code>/<year>/normalized.json` 保存

### CLI 例

```bash
python skills/expense-collect/normalize.py --year 2025
python skills/expense-collect/normalize.py --year 2025 --sites sbi nomura
```

---

## 検証

- [ ] SBI: 配当金 0 件以上抽出 (今回サンプルでは摘要に「配当金」明記なし、要実機確認)
- [ ] nomura: 配当金 5 件以上抽出 (取引区分 = "入金（配当金）")
- [ ] rakuten: 1515 行 → year=2025 でフィルタリング後の件数妥当
- [ ] 共通 JSON で配当金集計 (filter `category=dividend` → sum amount_in)

---

## 実装タスク

- [ ] `src/money_ops/normalizer/expense_csv.py` 新設
  - Transaction / NormalizedReport dataclass
  - カテゴリ正規化関数 (`classify`)
- [ ] `skills/expense-collect/parsers/sbi.py` 新設
- [ ] `skills/expense-collect/parsers/nomura.py` 新設
- [ ] `skills/expense-collect/parsers/rakuten.py` 新設 (encoding cp932)
- [ ] `skills/expense-collect/normalize.py` 新設 (CLI)
- [ ] `tests/expense_collect/test_parsers.py` 新設 (各 parser サンプル CSV → Transaction list 検証)
- [ ] 実機実行 → `normalized.json` 出力確認 + 配当金集計確認

---

## 注意事項

- 採取済 CSV は data/expenses/securities/<code>/<year>/raw/*.csv に存在
- rakuten の銘柄コード抽出は内容文字列を正規表現で抽出する想定 (実装時に再分析)
- 同一年に複数 raw/CSV がある場合 (sbi 2025 で 3 ファイル) は最新のみ使用
- カテゴリ正規化はベストエフォート、`category_raw` を保持して後段リカバリ可
