# #43 ブラウザプロファイル バックアップ・リストアツール

## 対象 issue

[#43](https://github.com/genba-neko/agent-skills-money-ops/issues/43)

---

## 背景

- 各 code 別 Chromium persistent profile（`~/.money-ops-browser/<code>/`）は OneDrive 外
- ディスク障害・誤削除・PC 移行時に喪失リスク
- バックアップ手段必要

---

## 仕様

### CLI

```bash
# 全 code バックアップ（デフォルト）
python tools/browser_profile.py backup
# → data/browser/all_2026-04-27.zip

# 特定 code バックアップ
python tools/browser_profile.py backup --code sbi
# → data/browser/sbi_2026-04-27.zip

# 全 code リストア（最新 all_*.zip 自動選択）
python tools/browser_profile.py restore
# → ~/.money-ops-browser/<各code>/ に展開

# 特定 code リストア（最新 sbi_*.zip 自動選択）
python tools/browser_profile.py restore --code sbi

# ファイル明示指定
python tools/browser_profile.py restore --file data/browser/sbi_2026-04-27.zip
```

### ファイル命名規則

- 全 code: `all_YYYY-MM-DD.zip`
- 特定 code: `{code}_YYYY-MM-DD.zip`
- 同日複数回 backup の場合は上書き

### バックアップ対象

- `~/.money-ops-browser/<code>/` ディレクトリ全体
- zip 内構造: `<code>/...` （展開時に `~/.money-ops-browser/` に解凍）

### リストア挙動

- 既存 profile を **上書き**（事前自動 backup なし）
- 復元前に確認プロンプト（破壊的操作のため）
- `--yes` で確認スキップ

### file lock 対策

- backup/restore 時に対象 code のブラウザ起動中だと失敗
- 起動中検知（lock ファイル等）→ 警告 + 続行可否確認

### alias

`.workbench/alias_rules` に追加:

```
browser-backup   $VENV_PYTHON $PROJECT_ROOT/tools/browser_profile.py backup @args   # ブラウザプロファイルバックアップ
browser-restore  $VENV_PYTHON $PROJECT_ROOT/tools/browser_profile.py restore @args  # ブラウザプロファイルリストア
```

---

## 実装タスク

- [x] `tools/browser_profile.py` 新設
  - argparse で backup / restore サブコマンド
  - backup: 全 or 単一 code を zip 化（空ディレクトリも entry 記録）
  - restore: 最新 zip 自動選択 or --file 指定
  - 上書き確認プロンプト + `--yes` オプション
- [x] `.workbench/alias_rules` に browser-backup / browser-restore 追加
- [x] 動作確認: backup → profile 削除 → restore で復元（diff -rq 完全一致確認済）

---

## 注意事項

- profile ディレクトリの code 一覧取得: `~/.money-ops-browser/` の subdir を列挙
- registry.json 参照は不要（profile が存在するもののみ対象）
- zip ライブラリ: `zipfile` （標準ライブラリ）

---

## 参考

- profile 保存先: `~/.money-ops-browser/<code>/`（base.py の `_browser_profile_dir`）
- バックアップ保存先: `data/browser/`
