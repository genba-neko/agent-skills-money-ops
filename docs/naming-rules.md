# プロジェクト命名規則

## 基本方針

| 対象 | 規則 | 例 |
|------|------|-----|
| ディレクトリ（データ置き場） | **複数形基準** + カテゴリ階層 | `data/{expenses,incomes}/<category>/<code>/<year>/raw/` |
| ディレクトリ（不可算 / 内容名） | 単数 OK（内容を表す名前） | `data/browser-backups/`（zip 置き場） |
| スキル名 | 単数（動作主体表現） | `tax-collect`, `expense-collect`, `tax-etax` |
| サイトコード | 小文字 + ハイフン区切り | `gmo-click`, `nomura-mochikabu`, `daiwa-connect` |
| Python ファイル名 | アンダースコア区切り（PEP 8 準拠） | `browser_profile.py`, `pdf_to_json.py` |
| Python パッケージ名 | アンダースコア区切り（PEP 8 準拠） | `money_ops/`, `tax_collect/` |
| テストファイル名 | サイトコードのハイフンは「くっつけ」 | `test_nomuramochikabu.py`, `test_gmoclick.py` |
| テスト配置 | スキル単位サブディレクトリ | `tests/tax_collect/test_sbi.py`, `tests/expense_collect/test_sbi.py` |
| ドキュメント | `docs/` 配下、内容ベース命名 | `docs/adb-setup.md`, `docs/naming-rules.md` |
| エイリアス（`.workbench/alias_rules`） | 機能ドメイン-動作 | `tax-collect`, `browser-backup`, `browser-restore` |

---

## 命名の意図と使い分け

### スキル名は単数

スキルは「動作主体」を表す。`expense-collect` = 「支出を収集する」という動詞句で、対象データの単複は問わない。

### データ置き場は複数 + カテゴリ階層

`data/expenses/` は「複数の支出データの集合」を保管する場所。REST API endpoint（`/users`, `/orders`）と同じ慣習。

直下に `<code>/` を置かず、必ず `<category>/<code>/<year>/raw/` の階層を取る:

```
data/
├── incomes/
│   ├── securities/<code>/<year>/raw/        # 証券会社
│   ├── crowdfunding/<code>/<year>/raw/      # クラウドファンディング
│   └── fx/<code>/<year>/raw/                # FX
└── expenses/
    ├── securities/<code>/<year>/raw/        # 証券会社の入出金明細
    └── cards/<code>/<year>/raw/             # クレジットカード（将来）
```

カテゴリ名は `incomes/`/`expenses/` 双方で統一。新規 code 追加時は `registry.json` に `category` field を持たせ、各 collector の `site.json` で `output_dir` に `<category>` を含める。

### 不可算名詞・内容名は単数

`browser-backups/` は「ブラウザプロファイルの zip backup ファイル群」を表す内容ベース命名。「browsers」だと「複数のブラウザ実体」を連想させミスリードのため避ける。

### サイトコードのハイフン

公式社名や略称の区切りに合わせる:

- ハイフンあり: `gmo-click`（GMO クリック証券）, `nomura-mochikabu`（野村持株）, `mufg-esmart`（MUFG e-Smart）
- ハイフンなし: `smbcnikko`（SMBC日興、慣用的にくっつけ）, `paypay`, `rakuten`, `monex` 等

### テストファイル名のハイフン処理

Python ファイル名はアンダースコア区切りが PEP 8 準拠。サイトコードのハイフンを `_` に変換すると単語境界が曖昧になるため、**くっつけ**に統一:

- `nomura-mochikabu` → `test_nomuramochikabu.py`（◯）
- `nomura-mochikabu` → `test_nomura_mochikabu.py`（×、運用がブレる）
- `gmo-click` → `test_gmoclick.py`（◯、既存実態）

### テスト配置（スキル単位サブディレクトリ）

複数スキルで同じサイト（例: SBI）のテストが衝突しないよう、スキル名のサブディレクトリで分離:

```
tests/
├── common/                      # 全スキル共通テスト
├── tax_collect/                 # tax-collect 専用
│   └── test_sbi.py
└── expense_collect/             # expense-collect 専用
    └── test_sbi.py
```

サブディレクトリ名はアンダースコア区切り（Python module 規則）、スキル名のハイフンは `_` に変換。

---

## 例外・保留事項

| 項目 | 状態 | 備考 |
|------|------|------|
| `src/money_ops/converter/generate_xml.py` の動詞型命名 | 保留 | 他は `X_to_Y` 型で揺れあり |
| `workbench/` と `.workbench/` の併存 | 保留 | 公開/隠しの役割整理は別途 |
| `output/` 配下の単複混在 | 保留 | 副産物置き場、整理優先度低 |
| `data/screenshots/` の配置 | 保留 | `output/` への移動は今回対象外 |
| `smbcnikko` のハイフン無し | 維持 | 意図的（慣用的にくっつけ） |

---

## 適用範囲

このルールは新規作成・既存リネーム時の指針。過去の `plan/` 配下のドキュメント等は履歴扱いで原文維持。
