# #45 プロジェクト命名規則の整理

## 対象 issue

[#45](https://github.com/genba-neko/agent-skills-money-ops/issues/45)

---

## 決定事項

| # | 項目 | 方針 |
|---|------|------|
| 1 | data/ 配下命名 | **複数形基準**（不可算は内容を表す名前へ） |
| 2 | テストファイル ハイフン処理 | **くっつけ統一** |
| 3 | converter/ 命名形式 | 保留 |
| 4 | workbench/.workbench | 対象外 |
| 5 | README_*.md 配置 | **docs/ に移動 + 内容ベース命名** |
| 6 | smbcnikko ハイフン無し | 意図的、保留 |
| 7 | converter/convert 動詞名詞 | 保留 |
| 8 | output/ 配下 | 今回対象外 |
| + | tax-recorder 汎用化 | **本対応で実施（browser-recorder にリネーム）** |
| + | 命名規則ドキュメント化 | **別ファイルで作成** |

---

## コミット分離（単一 PR）

レビュー単位はコミットで分割。各コミットは単独で動く・テスト通る粒度:

1. `chore: #45 docs/ 集約 + README_*.md 改名`
2. `chore: #45 命名規則ドキュメント追加 (docs/naming-rules.md)`
3. `refactor: #45 data/expense → data/expenses リネーム + 関連 path 修正`
4. `refactor: #45 data/browser → data/browser-backups リネーム + tools/browser_profile.py 修正`
5. `refactor: #45 data/income → data/incomes リネーム + tax-collect 全 site.json + base.py 修正`
6. `refactor: #45 tests/ をスキル単位サブディレクトリ化 + ファイル名整理`
7. `refactor: #45 tax-recorder → browser-recorder（tools/ 移動・改名）`

---

## 1. data/ 命名整理

### リネーム

- `data/expense/` → `data/expenses/`（実データ移行）
- `data/expenses/`（既存・空）→ 統合先
- `data/browser/` → `data/browser-backups/`（zip 置き場の内容を表す名前）
- `data/screenshots/` → そのまま（既に複数）

### コード修正対象

**expense → expenses**
- `skills/expense-collect/run.py`（docstring + is_collected）
- `skills/expense-collect/sites/sbi/site.json`
- `skills/expense-collect/sites/sbi/collect.py`
- `skills/expense-collect/SKILL.md`
- `skills/expense-collect/README.md`

**browser → browser-backups**
- `tools/browser_profile.py`（`_BACKUP_DIR = data/browser` → `data/browser-backups`）

### income → incomes（コミット 5）

- `data/income/` → `data/incomes/`
- `src/money_ops/collector/base.py:51` の hardcode 適正化（下記「## 5」参照）
- `skills/tax-collect/sites/*/site.json`（15ファイル、output_dir に `{year}` placeholder 化）
- `skills/tax-collect/{convert_worker.py,SKILL.md,README.md}` 等

### 過去 plan/ ファイル

- 履歴として原文維持。書き換えない。

---

## 2. テスト階層化 + ファイル名整理

### 背景

- `tax-collect` と `expense-collect` で同サイト（例: SBI）のテストが衝突する
- 現状フラット配置 → 将来 `test_sbi_collector.py` 1 つでは tax/expense 区別不能

### 新構成

```
tests/
├── conftest.py                ← 維持（PROJECT_ROOT/SITES_DIR）
├── fixtures/                   ← 維持
├── common/                     ← skill 共通テスト
│   ├── __init__.py
│   ├── test_base_collector.py
│   ├── test_collectors_all.py
│   ├── test_pdf_to_json.py
│   ├── test_xml_to_json.py
│   └── test_registry.py
├── tax_collect/                ← tax-collect 専用
│   ├── __init__.py
│   ├── test_sbi.py
│   ├── test_nomuramochikabu.py  ← ハイフンくっつけ + _collector suffix 削除
│   ├── test_daiwaconnect.py
│   ├── test_gmoclick.py
│   ├── test_mufgesmart.py
│   ├── test_smbcnikko.py
│   ├── test_paypay.py
│   ├── test_rakuten.py
│   ├── test_rakuten_selectors.py
│   ├── test_monex.py
│   ├── test_matsui.py
│   ├── test_hifumi.py
│   ├── test_tsumiki.py
│   ├── test_webull.py
│   ├── test_sawakami.py
│   └── test_nomura.py
└── expense_collect/            ← expense-collect 専用（将来用、現状空）
    └── __init__.py
```

### リネーム表（tax_collect/ 配下）

| 旧（tests/） | 新（tests/tax_collect/） |
|---|---|
| `test_sbi_collector.py` | `test_sbi.py` |
| `test_nomura_mochikabu_collector.py` | `test_nomuramochikabu.py` |
| `test_daiwaconnect_collector.py` | `test_daiwaconnect.py` |
| `test_gmoclick_collector.py` | `test_gmoclick.py` |
| `test_mufgesmart_collector.py` | `test_mufgesmart.py` |
| `test_smbcnikko_collector.py` | `test_smbcnikko.py` |
| `test_paypay_collector.py` | `test_paypay.py` |
| `test_rakuten_collector.py` | `test_rakuten.py` |
| `test_rakuten_selectors.py` | `test_rakuten_selectors.py` |
| `test_monex_collector.py` | `test_monex.py` |
| `test_matsui_collector.py` | `test_matsui.py` |
| `test_hifumi_collector.py` | `test_hifumi.py` |
| `test_tsumiki_collector.py` | `test_tsumiki.py` |
| `test_webull_collector.py` | `test_webull.py` |
| `test_sawakami_collector.py` | `test_sawakami.py` |
| `test_nomura_collector.py` | `test_nomura.py` |

### 確認

- pytest は parent `conftest.py` を子ディレクトリにも適用 → 動作 OK
- `git mv` でリネーム履歴保持
- 各 test ファイル内 import path 確認（プロジェクト内 module は影響なし見込み）

---

## 3. tax-recorder → browser-recorder 改名

### 背景

- recorder は汎用ツールだが、tax-collect 実装時に作ったため `skills/tax-collect/recorder.py` に配置
- alias 名 `tax-recorder` も tax 専用に見える
- browser-backup / browser-restore と揃え `browser-recorder` に統一

### 事前確認結果

- `recorder.py` 内部依存: `_PROJECT_ROOT = Path(__file__).resolve().parents[2]` のみ
- tax-collect sites/registry への参照なし → 完全独立で移動可
- 出力先: `output/recorder/<code>/<ts>/`（root 相対）→ 移動後も同じ場所に保存

### 対応

- `skills/tax-collect/recorder.py` → `tools/browser_recorder.py`（移動 + Python ファイル名はアンダースコア）
- 内部修正: `parents[2]` → `parents[1]`
- `.workbench/alias_rules`: `tax-recorder` → `browser-recorder` に rename + path 修正
- docstring 内 `python skills/tax-collect/recorder.py ...` → `python tools/browser_recorder.py ...` に更新

### 影響

- alias 名変更: `tax-recorder` → `browser-recorder`（後方互換不要、未公開）

---

## 4. docs/ 集約 + 命名規則ドキュメント化

### docs/ 新規作成

ルート散在の README_*.md を docs/ 配下に集約 + 内容ベース命名:

- `README_ADB.md` → `docs/adb-setup.md`（Android ADB 接続セットアップ手順）
- `README_PDFCONV.md` → `docs/pdf-extraction-benchmark.md`（PDF→テキスト変換ベンチマーク）
- `docs/naming-rules.md`（新規）

ルート `README.md` はそのまま維持。

### 命名規則ドキュメント (`docs/naming-rules.md`) 内容

- ディレクトリ命名: 複数形基準（`expenses/`, `incomes/`, `screenshots/`）
- 不可算名詞または「内容を表す名前」が適切な場合は単数 OK（`browser-backups/` は内容名）
- スキル名: 単数（動作主体表現）。例: `tax-collect`, `expense-collect`
- サイトコード: ハイフン区切り。例: `gmo-click`, `nomura-mochikabu`
- Python ファイル名: アンダースコア（PEP 8 準拠）
- テストファイル名: サイトコードのハイフンは「くっつけ」
- 例外・保留事項記載

---

## 5. base.py の output_dir hardcode 適正化

### 現状（問題）

`src/money_ops/collector/base.py:51`:
```python
self.config["output_dir"] = f"data/income/securities/{self.code}/{year}/raw/"
```

→ tax-collect 専用 path が base.py に hardcode。expense-collect は subclass で override 必要だった（PR#42）。

### 対応

site.json 側で `{year}` placeholder 化、base.py で format:

**site.json（全 16 ファイル: tax-collect 15 + expense-collect 1）**
```json
{ "output_dir": "data/incomes/securities/sbi/{year}/raw/" }
```

**base.py 修正案**
```python
self.output_dir = Path(self.config["output_dir"].format(year=self.config["target_year"]))
if year is not None:
    self.config["target_year"] = year
    self.output_dir = Path(self.config["output_dir"].format(year=year))
```

### 効果

- base.py から tax-collect 専用 path 消滅
- expense-collect の subclass override 削除可（`skills/expense-collect/sites/sbi/collect.py` の `__init__` 簡略化）
- 将来追加サイトも site.json だけで完結

### 影響範囲

- `src/money_ops/collector/base.py`
- `skills/tax-collect/sites/*/site.json`（15）
- `skills/expense-collect/sites/sbi/site.json`（1）
- `skills/expense-collect/sites/sbi/collect.py`（subclass override 削除）

→ コミット 5 に統合（`income→incomes` リネームと一緒に実施）

---

## 実装タスク

- [ ] **コミット 1**: `docs/` 作成 + README_*.md 移動・改名
  - [ ] `README_ADB.md` → `docs/adb-setup.md`
  - [ ] `README_PDFCONV.md` → `docs/pdf-extraction-benchmark.md`
- [ ] **コミット 2**: `docs/naming-rules.md` 作成
- [ ] **コミット 3**: data/expense → expenses
  - [ ] 実データ mv（既存 data/expenses/cards/ と統合）
  - [ ] `expense-collect` 配下 path 一括置換
- [ ] **コミット 4**: data/browser → browser-backups
  - [ ] 実データ mv
  - [ ] `tools/browser_profile.py` の `_BACKUP_DIR` 修正
- [ ] **コミット 5**: data/income → incomes + base.py hardcode 適正化
  - [ ] 実データ mv
  - [ ] `src/money_ops/collector/base.py` の output_dir 解決を `{year}` placeholder format 化
  - [ ] `skills/tax-collect/sites/*/site.json` 全15サイト: output_dir を `data/incomes/.../{year}/raw/` に変更
  - [ ] `skills/expense-collect/sites/sbi/site.json`: output_dir を `data/expenses/.../{year}/raw/` に変更
  - [ ] `skills/expense-collect/sites/sbi/collect.py`: subclass override 削除
  - [ ] `skills/tax-collect/{convert_worker.py,SKILL.md,README.md}` path 修正
- [ ] **事前確認 (コミット 6 前)**: 全 `tests/test_*.py` の import / class 参照確認（プロジェクト内 module 名に影響あるか grep）
- [ ] **コミット 6**: tests/ スキル単位サブディレクトリ化
  - [ ] `tests/{common,tax_collect,expense_collect}/__init__.py` 作成
  - [ ] 共通テスト 5件 → `tests/common/` に `git mv`
  - [ ] tax-collect サイトテスト 16件 → `tests/tax_collect/` に `git mv` + `_collector` suffix 削除 + ハイフンくっつけ統一
  - [ ] `pytest tests/` で全テスト discovery 確認
- [ ] **コミット 7**: tax-recorder → browser-recorder
  - [ ] `skills/tax-collect/recorder.py` → `tools/browser_recorder.py`
  - [ ] `parents[2]` → `parents[1]` 修正
  - [ ] docstring 修正:
    - line 1: `tax-collect サイト追加用` → `サイト追加用`
    - line 4: `python skills/tax-collect/recorder.py` → `python tools/browser_recorder.py`
  - [ ] `.workbench/alias_rules`: `tax-recorder` → `browser-recorder`
- [ ] 動作確認
  - [ ] `python tools/browser_profile.py backup --code sbi --yes` → `data/browser-backups/sbi_*.zip`
  - [ ] `python tools/browser_recorder.py --code dummy --start-url about:blank`（起動確認）
  - [ ] `pytest tests/`（全テスト通過）
  - [ ] **必須**: `python skills/expense-collect/run.py --year 2025 --sites sbi --force` → `data/expenses/sbi/2025/raw/` に CSV 出力確認

---

## 注意事項

- **plan/ ファイルは履歴扱いで書き換えない**
- 既存 data/ の実データは git ignore 対象 → mv のみ、コミット不要
- 各コミット単独でテスト通る粒度を守る
