# recorder.py に「ユーザー入力・select 値変更」記録機能を追加 [完了 PR#40 2026-04-27]

## 背景

saison-am 実装（PR#38）でわかったこと:

- recorder は **結果**（URL 遷移・DOM スナップショット・network）を記録する
- **中間の手動操作**（select 値変更・button click 順序・input fill）は記録しない
- ユーザーが手動で「報告書種類変更」「検索 click」した部分は recorder 出力に残らない
- → recorder データだけ見ても「どの dropdown で何を選んだか」分からない
- → 実装中にトライアンドエラーが多発し、実装完了まで 10 回以上の試行錯誤が必要だった

## 解決方針

Playwright が提供する codegen 同等機能を recorder.py に組み込み、ユーザー操作を時系列で記録する。

### 実装案

**A. context.set_default_timeout + 操作 hook（軽量）**

各 page に DOM event listener を attach:
- `click` イベント → element selector + text を記録
- `input/change` イベント → field name + value を記録
- `submit` イベント → form name を記録

ただしこれは DOM event なので Playwright 経由じゃない実 click は拾えない。

**B. Playwright codegen の `--target=python` を活用（推奨）**

`playwright codegen` は実 click/input をすべて Python 形式で出力する。これを recorder と並行起動:

1. recorder.py がブラウザ起動
2. 同時に `playwright codegen` を attach するか、または `inspector` モードで起動
3. ユーザー操作 → Playwright 内部で codegen がスクリプト生成
4. recorder 終了時に codegen 出力（actions.py）を保存

調査必要: Playwright Python で codegen を programmatic に有効化できるか？
- `npx playwright codegen --target=python URL` 形式は別プロセス
- recorder の persistent context と統合可能か要検証

**C. trace.zip 解析後処理（最も確実）**

trace.zip には全 Playwright 操作（click/input/select 等）が含まれる。
ただし trace は Playwright API 経由の操作のみ記録 = ユーザー手動操作は **記録されない**。

→ B 案が本命だが、技術的検証必要

**D. context.expose_binding でカスタム binding を仕込む**

recorder.py 起動時、各 page に JavaScript を inject:
- click handler で `window.__recorder_click(selector, text)` 呼び出し
- change handler で `window.__recorder_change(name, value)` 呼び出し
- expose_binding で Python 側に通知 → events.jsonl に記録

実装簡単・確実。selector 生成は `getXPath` 等で要工夫。

## 推奨実装: D 案

### 仕様

- recorder.py に 4 種の event 追加:
  - `user_click`: clicked element の tag, role, text, name 属性
  - `user_input`: input/textarea の name, value（パスワードはマスク）
  - `user_change`: select の name, selected value/text
  - `user_submit`: form の name, action
- 既存 events.jsonl に時系列で追記
- summary.md に「ユーザー操作」セクション追加

### inject する JS（疑似）

```javascript
document.addEventListener('click', (e) => {
  const el = e.target;
  window.__recorder_event('user_click', {
    tag: el.tagName,
    text: el.textContent.slice(0, 100),
    role: el.getAttribute('role'),
    name: el.getAttribute('name') || el.id,
    selector: getCssPath(el),  // 自前で書く
  });
}, true);

document.addEventListener('change', (e) => {
  const el = e.target;
  if (el.tagName === 'SELECT') {
    window.__recorder_event('user_change', {
      name: el.name || el.id,
      value: el.value,
      selectedText: el.options[el.selectedIndex]?.text,
    });
  } else if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
    const isPassword = el.type === 'password';
    window.__recorder_event('user_input', {
      name: el.name || el.id,
      value: isPassword ? '***MASKED***' : el.value.slice(0, 200),
      type: el.type,
    });
  }
}, true);

document.addEventListener('submit', (e) => {
  window.__recorder_event('user_submit', {
    name: e.target.name,
    action: e.target.action,
  });
}, true);
```

### Python 側

```python
def _on_recorder_event(source, kind, data):
    add_event(kind, **data)

context.expose_binding("__recorder_event", _on_recorder_event)
context.add_init_script(JS_LISTENERS)  # 上記 JS を全 page に inject
```

## 実装タスク

1. `recorder.py` に inject する JS 文字列を追加
2. `context.expose_binding` + `context.add_init_script` で全 page に hook 適用
3. add_event の対応 kind 追加（user_click / user_input / user_change / user_submit）
4. summary.md に「ユーザー操作」セクション追加（時系列で操作ログ表示）
5. 動作確認: 既存 saison-am サイトで再 recorder 実行して操作ログ取れるか確認

## 注意

- パスワードフィールドは値マスク必須
- text/value は長くなりすぎないよう truncate（200 chars）
- popup や iframe にも init_script 適用（context レベル設定で OK）
- 既存 recorder 出力との互換性維持（events.jsonl に kind 追加するだけ）
