# #47 browser_recorder のブラウザ × 閉じ時 trace.zip 救済

## 対象 issue

[#47](https://github.com/genba-neko/agent-skills-money-ops/issues/47)

---

## 背景

`tools/browser_recorder.py` は `q+Enter` / Ctrl+C 停止時は trace.zip / network.har 保存される。
しかしユーザーがブラウザ × 閉じで終了すると `tracing.stop()` が context closed 後にしか呼べず、
`Tracing.stop: Target page, context or browser has been closed` エラーで保存失敗。

PR #46 実機テスト (nomura) で再現確認:
```
[recorder] tracing 停止失敗（ブラウザ閉じ）: Tracing.stop: Target page, context or browser has been closed
```

私 (Claude) が recorder を起動する運用パターン (TTY なし) では `q+Enter` 不可
→ ブラウザ × 閉じが通常終了になる必要がある → 現状仕様で trace.zip / HAR 失われる。

---

## 解決方針 (L 案)

Playwright doc 調査結果:
- `tracing.start(live=True)`: trace を real-time で **unarchived file に書き込む** (cache → close 時 zip 化方式ではない)
- `launch_persistent_context(traces_dir=...)`: 中間 trace files の保存先指定
  - 公式 doc: 「The directory is not cleaned up when the browser closes」

→ ブラウザ × 閉じても disk に trace データが残る。

---

## 実装

### 1. browser_recorder.py 修正

```python
# context 作成時 traces_dir 指定
launch_kwargs = {
    "headless": False,
    "traces_dir": str(out_dir / "traces"),  # 中間 trace 保存先
    ...
}
context = playwright.chromium.launch_persistent_context(profile_dir, **launch_kwargs)

# tracing 開始時 live=True
context.tracing.start(screenshots=True, snapshots=True, sources=True, live=True)
```

`tracing.stop()` 試行は維持 (q+Enter 停止時は zip 化される)。
失敗時は traces_dir に残る trace データの確認方法を案内。

### 2. HAR 同等救済可否

- `record_har_path` は context 作成時指定 → close 時 flush
- ブラウザ × 閉じ時の HAR 救済方法は要調査（Playwright API 制約により困難な可能性高）
- 救えなければ HAR は trace.zip 内 network 情報で代替可能 (live trace に network 含まれる)

### 3. 起動時メッセージ改善

trace データ救済可能を明示:
```
[recorder] trace データは traces/ 配下に逐次保存されます (live mode)
[recorder] q+Enter で停止すると zip 化、× 閉じでも traces/ 内に残ります
```

---

## 検証

- [ ] **q+Enter 停止 → 従来通り trace.zip 化される** (未検証)
  - 理由: Claude (Bash) 経由起動だと TTY なし = q+Enter 不可、検証不能
  - 既存挙動なので回帰なしの想定。ユーザ手動 terminal で確認推奨
- [x] **ブラウザ × 閉じ → traces/ 配下に unarchived trace データ残る**
  - google.com で検証 → `recording.trace` 2.8MB / `recording.network` 1.3MB / `resources/` 残存
- [x] **Trace Viewer 動作確認**
  - `npx playwright show-trace trace.zip` で再生 OK
  - 22秒分スクショ・network 233件・操作 timeline 完全再現確認
- [x] **HAR 救済可否確認**
  - × 閉じ時 `network.har` ファイル自体作成されない
    （Playwright が close 時 flush するため）
  - 代替: trace.zip 内 network 情報で完全代替可能

---

## 実装タスク

- [x] `tools/browser_recorder.py` 修正
  - [x] `launch_kwargs` に `traces_dir` 追加
  - [x] `tracing.start(name="recording", ...)` 化
  - [x] 起動時メッセージ更新（× 閉じでも trace 残る案内）
  - [x] 追加: main loop で全 page closed 検知 → stop（context.on("close") 不発火対策）
  - [x] 追加: tracing.stop 失敗時 traces/ → trace.zip 自動 zip 化
- [x] empirical test (google.com で実施)
  - [x] × 閉じ → traces/ 配下に recording.trace / .network / resources/ 残存
  - [x] Trace Viewer (`npx playwright show-trace trace.zip`) で再生 OK
    （22秒分スクショ・network 233件・操作 timeline 完全再現）
  - [x] 自動 zip 化後の trace.zip 4.9MB 生成
- [x] HAR の挙動調査済
  - × 閉じ時 `network.har` ファイル自体作成されない（Playwright が close 時 flush するため）
  - 代替: trace.zip 内 network 情報で完全代替可能
    （Trace Viewer の Network タブで実機 233 件のリクエスト確認済）
  - HAR ファイル独立救済は Playwright API 制約により不可、対応見送り
- [x] プラン完了マーク

---

## 注意事項

- recorder.py は tools/ 配下に PR #46 で移動済み (本プランは PR #46 マージ後の master ベース)
- 副作用ゼロ要件: サイト挙動への影響なし、event 捕捉機能を劣化させない
- 採取機能維持: trace.zip / events.jsonl / DOM dump は既存通り
