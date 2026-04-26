# #36 セゾン投信 特定口座年間取引報告書 自動収集スクリプト実装

## 対象 issue

[#36](https://github.com/genba-neko/agent-skills-money-ops/issues/35)

---

## 背景

セゾン投信（saison-am）は tax-collect 未対応。Webアプリ＋電子バト（denshi-bato）系のPDF配信システムを使用。`recorder.py` でフロー調査済み。

---

## 操作データ（recorder 出力）

`output/recorder/saison-am/20260426_120247/`
- `summary.md` — URL 推移・popup・download 要約
- `events.jsonl` — 全イベント時系列
- `network.har` — リクエスト・レスポンス・cookie
- `trace.zip` — Playwright Trace Viewer 用
- `dom_*.html` — milestone 地点 DOM

---

## フロー（実測）

```
www.saison-am.co.jp (トップ)
  ↓ ログイン
  popup: app.saison-am.co.jp/mypage  (会員ページ)
  ↓ 取引 → 取引パスワード入力
  popup: trade.saison-am.co.jp/webbroker3/Web3SZApp?SZkey=...
  ↓
  popup: w37.denshi-bato.webbroker.jp/seciss/denshibato
         ?REPORTTYPE=3&SERCHPDF=2025/12/31
  ↓ PDFファイル取得
  download: 270582202512313_YYYYMMDDHHMMSS.pdf
```

---

## 実装方針

### popup チェーン管理

4 段階の popup 遷移:
1. `www.saison-am.co.jp` → `app.saison-am.co.jp/mypage` （ログイン後）
2. `app.saison-am.co.jp` → `trade.saison-am.co.jp/webbroker3/Web3SZApp` （取引パスワード）
3. `trade.saison-am.co.jp` → `w37.denshi-bato.webbroker.jp/seciss/denshibato`
4. PDF download

各 popup は `expect_popup()` で待機（CDP イベントポンプ維持）。

### 手動介入ポイント

- ログイン（ID/PW）
- 取引パスワード（page2）
- 二段階認証（必要時）

→ `wait_for_url("**/app.saison-am.co.jp/mypage**", timeout=300_000)` でログイン完了検知

### PDF 取得方式

- 配信元: `w37.denshi-bato.webbroker.jp/seciss/denshibato`
- e-shishobako（hifumi 等）と類似アーキテクチャ → `capture_dpaw_pdf` 流用検討
- ただし URL pattern 異なる可能性 → HAR で詳細確認後判定
- クエリ: `REPORTTYPE=3` (年間取引報告書), `SERCHPDF=YYYY/12/31`

### 報告書年度指定

`SERCHPDF=2025/12/31` を `--year` 引数から組み立て。

---

## 実装タスク

1. `skills/tax-collect/sites/saison-am/` ディレクトリ作成
2. `site.json` 作成（login_url, target_year 等）
3. `collect.py` 作成（BaseCollector 継承）
   - `_wait_for_login`
   - `_navigate_to_denshibato` （popup 4 段階）
   - PDF 捕捉（capture_dpaw_pdf or 専用実装）
4. `registry.json` に saison-am 追加（collection: auto）
5. 動作確認（`python skills/tax-collect/sites/saison-am/collect.py --year 2025`）
6. 一括ランナー経由確認（`python skills/tax-collect/run.py --sites saison-am --year 2025`）

---

## 参考

- recorder 出力: `output/recorder/saison-am/20260426_120247/`
- 類似実装: `skills/tax-collect/sites/hifumi/collect.py`（e-shishobako）
- 共通モジュール: `src/money_ops/collector/eshishobako.py`（capture_dpaw_pdf）
