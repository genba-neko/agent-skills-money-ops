# #48 is_collected 単体テスト追加

## 対象 issue

[#48](https://github.com/genba-neko/agent-skills-money-ops/issues/48)

---

## 背景

PR #46 で `data/income → data/incomes` リネーム時、Path 連結形式 `Path("data") / "income"` で書かれた is_collected の path 修正が漏れ、tax-collect の収集済み判定が常に False（--force 等価）になる不具合発生。実機確認まで検出できなかった。

→ 両 collector の `is_collected` に単体テスト追加で path リネーム時の回帰検出を担保。

---

## 対象関数

### 1. `skills/tax-collect/run.py:45` — `is_collected(category, code, year)`

```python
def is_collected(category: str, code: str, year: int) -> bool:
    json_path = (
        _PROJECT_ROOT / "data" / "incomes" / category
        / code / str(year) / "nenkantorihikihokokusho.json"
    )
    return json_path.exists() and json_path.stat().st_size > 0
```

### 2. `skills/expense-collect/run.py:44` — `is_collected(category, code, year)`

```python
def is_collected(category: str, code: str, year: int) -> bool:
    raw_dir = _PROJECT_ROOT / "data" / "expenses" / category / code / str(year) / "raw"
    if not raw_dir.exists():
        return False
    return any(raw_dir.glob("*.csv"))
```

---

## 実装方針

両 run.py とも `_PROJECT_ROOT` モジュール変数を持つ → `monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)` で差し替え。
ダミーファイル配置 → is_collected 呼び出し → 戻り値検証。

importlib で `run.py` をロード（`run` という名前は他とぶつかる可能性あり、prefix 付与）。

---

## 検証ケース

### `tests/tax_collect/test_run.py` (新設)

- [ ] 存在 + サイズあり → True
- [ ] 存在するが空ファイル (size 0) → False
- [ ] 存在しない → False
- [ ] category 違い (securities 配置 → crowdfunding 検索) → False
- [ ] year 違い (2025 配置 → 2024 検索) → False
- [ ] **path 構造検証**: `data/incomes/<category>/<code>/<year>/nenkantorihikihokokusho.json` であることを確認 (リネーム時の回帰検出)

### `tests/expense_collect/test_run.py` (新設)

- [ ] CSV 存在 → True
- [ ] raw/ 存在するが CSV なし (txt のみ等) → False
- [ ] raw/ 存在しない → False
- [ ] category 違い → False
- [ ] **path 構造検証**: `data/expenses/<category>/<code>/<year>/raw/*.csv`

---

## 実装タスク

- [ ] `tests/tax_collect/test_run.py` 新設（6 ケース）
- [ ] `tests/expense_collect/test_run.py` 新設（5 ケース）
- [ ] pytest 全件パス確認
- [ ] プラン完了マーク + コミット + PR

---

## 注意事項

- 既存の collector module 直接 import は避け、`importlib.util.spec_from_file_location` で run.py をロード
- `_PROJECT_ROOT` は monkeypatch で tmp_path 差し替え
- 副作用なし: 既存テストに影響なし
