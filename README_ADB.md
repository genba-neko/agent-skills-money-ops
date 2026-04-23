# Android ADB 接続セットアップ手順

動作確認環境: Windows 10 / OPPO Reno 10 (Android 13) / 2026-04-23

**USB 接続推奨**: ワイヤレスは接続が頻繁に切断される（ポートも毎回変わる）。スクリプト実行には USB 接続が安定。

---

## 1. ADB インストール（Windows）

```powershell
winget install Google.PlatformTools
```

> **注意**: インストール後、`adb` コマンドが認識されない場合がある。
> winget の portable インストールは PATH が通らないことがある。

### PATH が通っていない場合

実際の adb.exe の場所を探す:

```powershell
Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "adb.exe" | Select-Object FullName
```

見つかったパスを `.workbench/alias_rules` に追加:

```
adb  C:\Users\<ユーザー名>\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe @args
```

または永続的に PATH に追加:

```powershell
$adbDir = "C:\Users\g\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools"
[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$adbDir", "User")
```

インストール確認:

```powershell
adb version
# Android Debug Bridge version 1.0.41 が出ればOK
```

---

## 2. USB 接続（推奨）

ワイヤレスより安定。ケーブル1本でポート固定・切断なし。

### Android 側の設定

1. 開発者向けオプションを有効化（→ 下記参照）
2. 設定 → その他の設定 → 開発者向けオプション → **USB デバッグ** → ON

### PC に接続

1. USB ケーブルで接続
2. Android に「USB デバッグを許可しますか？」→ **許可**（「このPCを常に許可」推奨）

```powershell
adb devices
# 3d34b41d  device  ← シリアルが出れば完了
```

> シリアルは固定。以降は再接続不要（ケーブルを抜き差ししない限り）。

---

## 3. Android 側の設定（共通）

### 開発者向けオプションを有効化

OPPO Reno 10 の場合:

1. 設定 → 端末情報
2. **ビルド番号を7回タップ** → 「開発者向けオプションが有効になりました」

---

## 4. ワイヤレス接続（サブ）

ワイヤレスを使う場合のみ。

### ワイヤレスデバッグを有効化

1. 設定 → その他の設定 → 開発者向けオプション
2. **ワイヤレスデバッグ** → ON（トグル）
3. 「ワイヤレスデバッグ」の**文字部分をタップ**（トグルではなく）して詳細画面へ

---

## 5. ペアリング（ワイヤレス・初回のみ）

### Android 側

「ワイヤレスデバッグ」詳細画面 → **「デバイスのペアリング（ペアリングコードを使用）」** をタップ

→ IPアドレス・ポート番号・6桁コードが表示される

> **注意**: コードの有効期限は短い（数十秒程度）。表示されたらすぐに PC 側で実行する。

### PC 側

```powershell
adb pair <AndroidのIP>:<ペアリング画面のポート番号>
# Enter pairing code: と聞かれたら6桁コードを入力
# Successfully paired to ... が出ればOK
```

> **ハマりポイント**:
> - ポート番号はペアリング画面に表示されるもの（例: `43387`）を使う
> - コードが切れたら Android 側で再タップして新しいコード/ポートを取得
> - `error: protocol fault` が出たらコード期限切れ → 再取得

---

## 6. ワイヤレス接続

ペアリング成功後、接続に使うポートは**ワイヤレスデバッグのメイン画面**に表示される「IPアドレスとポート」。

> ペアリングのポートと接続のポートは**別物**。

```powershell
adb connect <AndroidのIP>:<メイン画面のポート番号>
# connected to 192.168.x.x:xxxxx が出ればOK

adb devices
# 192.168.x.x:xxxxx  device が出れば接続完了
```

---

## 7. ワイヤレス再接続（2回目以降）

ペアリングは不要。接続だけ実行:

```powershell
adb connect 192.168.2.196:39513
adb devices
```

> **注意**: Android を再起動するとポート番号が変わる場合がある。
> ワイヤレスデバッグ画面で現在のポートを確認してから接続。

---

## 8. mitmproxy と併用する場合の注意

Android の Wi-Fi プロキシを mitmproxy に向けている間は:

- ADB の接続が切れる場合がある（プロキシ経由でネットワークが不安定になる）
- ウィブル等のピンニングしているアプリの通信はブロックされる

**mitmproxy 使用後は必ずプロキシを「なし」に戻す**:

設定 → Wi-Fi → 接続中のSSID → プロキシ → **なし**

プロキシを無効にすると ADB 接続が切れるため、再接続が必要:

```powershell
adb connect 192.168.2.196:39513
```

---

## 動作確認

接続後、以下で画面の UI 構造を取得できる:

```powershell
adb shell uiautomator dump
adb pull /sdcard/window_dump.xml
```

`window_dump.xml` に現在の画面の要素一覧が出力される。
