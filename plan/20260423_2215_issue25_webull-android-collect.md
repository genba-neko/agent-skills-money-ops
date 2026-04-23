# #25 ウィブル証券 uiautomator2 Android自動収集スクリプト実装 [完了 PR#26 2026-04-23]

## 対象 issue

[#25](https://github.com/genba-neko/agent-skills-money-ops/issues/25)

---

## 背景

ウィブル証券はWebアプリが存在せず、Androidアプリのみ。
Playwright による収集が不可能なため、ADB + uiautomator2 でアプリを直接操作して収集する。

---

## 技術調査（実施済み）

### mitmproxy による API 傍受 → 断念

- Android の Wi-Fi プロキシを mitmproxy に向けることでトラフィック傍受を試みた
- ウィブル証券アプリは証明書ピンニングを実装しており、API通信のインターセプトは不可
- act.webull.co.jp（WebView）の通信は通過するが、取引/書類APIは直接通信

### uiautomator2 採用

- USB/ワイヤレスADB経由でAndroidアプリのUI要素を操作できる
- 証明書ピンニングの影響を受けない（UIレイヤー操作）
- `adb shell uiautomator dump` でUI構造をXMLダンプして実装

---

## UI構造（uiautomator dump 確認済み）

### ナビゲーションパス

```
ボトムバー: view_bottom_item（取引タブ・中央）
  → タブ: tabTitle="帳票"
    → 履歴記録（tv_date="履歴記録"）クリック
      → 全書類一覧（title_tv="履歴"）
        → recyclerView 内の各行
          - tv_name: 書類名
          - tv_date: 日付（特定口座年間取引報告書は "2025" のみ）
          - llPDFContainer: PDF アイコン
```

### 行タップ後の遷移

```
WebView（resource-id=webview）でPDF表示
  → r2_menu_icon タップ
    → フォルダ権限ダイアログ（2段階）:
        1. 「このフォルダを使用」
        2. 「許可」
      → /sdcard/Documents/{date}.pdf に保存
```

### ファイル命名規則

| 書類 | ファイル名例 |
|---|---|
| 特定口座年間取引報告書（2025年） | `2025-12-31.pdf` |
| 取引残高報告書（2025/12） | `2025-12.pdf` |
| 重複時 | `2025-12-31 (1).pdf`, `(2).pdf`, ... |

---

## 実装

### 収集フロー

1. アプリ起動（monkey）
2. 認証が必要な場合 → 手動ログイン待ち（input()）
3. 帳票タブ → 履歴記録
4. XPath で `tv_name="特定口座年間取引報告書"` かつ `tv_date="2025"` の行を探す
5. スクロールしながら最大15回探索
6. 行タップ → WebView 待機
7. `r2_menu_icon` タップ
8. 権限ダイアログ（2段階）を最大10秒ポーリングして自動タップ
9. `/sdcard/Documents/` + `/sdcard/Download/` の差分でダウンロードファイル特定
10. `adb pull` でローカル転送
11. `convert_pdf_to_json()` でJSON変換
12. `am force-stop` でアプリ終了

### ADB 接続

- USB 接続推奨（ワイヤレスはポート毎回変わり切断頻発）
- シリアル: `3d34b41d`（固定）
- 手順: README_ADB.md 参照

---

## 新規作成ファイル

```
skills/tax-collect/sites/webull/
├── site.json
└── collect.py
README_ADB.md
```

---

## 検証結果

```
[ウィブル証券] PDF 保存: data/income/securities/webull/2025/raw/2025_webull_nentori.pdf
[ウィブル証券] JSON 保存: data/income/securities/webull/2025/nenkantorihikihokokusho.json
[ウィブル証券] アプリ終了
```

