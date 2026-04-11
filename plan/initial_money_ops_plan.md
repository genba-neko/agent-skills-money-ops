# Money-OPSプロジェクトのセットアップ

## 概要

Claude Code と Chrome 拡張連携を使って、普段の明細保存や家計管理などの雑務や年次の確定申告などを行うAgent Skillsを実現するプロジェクト。
・確定申告（複数の証券会社、FX,クラウドファンディングなどから年間取引報告書およびそれに相当する情報の採取・保存、確定申告書の作成、確定申告の実施を担う）
・クレカ明細（各クレカ会社の明細を保存する）
・ポイ活やキャンペーンなどの管理（案件の管理、対応状況の管理など）
など、普段人間が行っていたことを代替し処理できることを目的にしている。機能は順次追加していく。

## 環境

- OS: Windows ネイティブ
- ブラウザ: Chrome 拡張連携で使用
- Python 環境: あり
- リポジトリ: プライベート GitHub リポジトリで管理

---

## Issue一覧

| # | 内容 | 状態 |
|---|---|---|
| [#1](https://github.com/genba-neko/agent-skills-money-ops/issues/1) | プロジェクト初期セットアップ（構成・CLAUDE.md・plugin.json） | [完了 PR#2 2026-04-11] |

---

## 実装内容

### issue #1: プロジェクト初期セットアップ

#### フォルダ構成

```
agent-skills-money-ops/
├── plugin.json
├── README.md
├── CLAUDE.md
├── .gitignore
├── plan/                        # プラン保存（git管理）
├── skills/
│   ├── tax-collect/             # 証券・FX・CF等から年間報告書収集
│   │   ├── SKILL.md
│   │   └── sites/               # サービス別設定（今後追加）
│   ├── tax-calc/                # 所得・税額計算
│   │   └── SKILL.md
│   ├── tax-etax/                # e-Tax記入・提出
│   │   └── SKILL.md
│   └── tax-review/              # 申告前最終確認
│       └── SKILL.md
├── data/                        # ★コミット禁止（個人情報）
│   ├── income/
│   │   ├── securities/          # 証券会社別
│   │   ├── fx/                  # FX会社別
│   │   └── crowdfunding/
│   ├── expenses/
│   │   └── cards/               # クレカ会社別
│   └── screenshots/
├── output/                      # ★コミット禁止
├── src/
│   └── money_ops/               # 共通Pythonパッケージ
│       └── __init__.py
└── tests/
    ├── __init__.py
    └── fixtures/                # モックデータ（個人情報なしのサンプルのみ）
```

#### plugin.json

```json
{
  "name": "agent-skills-money-ops",
  "version": "0.1.0",
  "description": "確定申告・家計・投資自動化スキル集",
  "skills": [
    "skills/tax-collect",
    "skills/tax-calc",
    "skills/tax-etax",
    "skills/tax-review"
  ]
}
```

#### CLAUDE.md に含めたルール

- 作業分担（人間 / Claude）
- プラン作成フロー・Issue登録・実装フロー
- ブランチ命名規則・Conventional Commits
- `git add .` 禁止・コミット禁止ファイルの明示
- 破壊的操作の鉄則（事前説明・安全側優先・2ステップ順序保証）
- セキュリティ・個人情報ルール（ハードコード禁止・マイナンバー記載禁止）
- ブラウザ自動操作ルール（1〜3秒wait・2FA/CAPTCHA時は即停止）
- Python開発ルール（src/money_ops + tests/構成・pytest）
- スキル開発ルール（prefix命名・plugin.json連動）

#### スキル命名方針

- prefix でドメインを示す（`tax-*` / `expense-*` 等）で命名衝突を防ぐ
- 今フェーズは確定申告系（`tax-*`）から実装する

---

## 制約・注意事項

- ログイン情報（ID・パスワード）はスクリプト内にハードコード禁止
- 個人情報（マイナンバー・口座番号）はいかなるファイルにも記載しない
- Playwright を使う場合は headless=False で動作確認してから headless 化
- 並列収集（Subagents）に対応できる設計にすること
