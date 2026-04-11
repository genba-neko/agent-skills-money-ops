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

## やってほしいこと

### 1. プロジェクト構成の作成

以下のようにフォルダ構成を考えてほしい。以下は正解ではなく、あくまでリポジトリからスキルインストールを想定した構造を示したものである。
フォルダ構成はディスカッションしながら決める。概要をもとに考える。

```
my-skills/
├── plugin.json
├── README.md
├── CLAUDE.md
├── .gitignore
├── skills/
│   ├── browser-collect/
│   │   ├── SKILL.md
│   │   └── sites/
│   ├── expense-categorize/
│   │   └── SKILL.md
│   ├── tax-income-calc/
│   │   └── SKILL.md
│   ├── pdf-fill-etax/
│   │   └── SKILL.md
│   └── final-review/
│       └── SKILL.md
├── data/
│   ├── income/
│   ├── expenses/
│   └── screenshots/
├── output/
└── scripts/
    ├── aggregate.py
    └── normalize.py
```

### 2. plugin.json の作成

claude plugin install で一発インストールできるようにする。以下は正解ではなく、あくまでリポジトリからスキルインストールを想定した構造を示したものである。

```json
{
  "name": "my-skills",
  "version": "1.0.0",
  "description": "確定申告・家計・投資自動化スキル集",
  "skills": [
    "skills/browser-collect",
    "skills/tax-income-calc",
    "skills/expense-categorize",
    "skills/pdf-fill-etax",
    "skills/final-review"
  ]
}
```

### 3. CLAUDE.md の作成

以下の内容を含めること。

- プロジェクト進行ルール（ディスカッションして確定）
- Git 操作のルール（git add . 禁止、ファイル個別指定）
- 絶対コミット禁止ファイルの明示（data/, output/, *.config.yaml, .env 等）
- 個人情報・マイナンバーをログ出力禁止
- ブラウザ操作時のレート制限対策（各操作間 1〜3 秒 wait）
- 2FA・CAPTCHA が出たら即座にユーザーに手動介入を依頼

---

## 制約・注意事項

- ログイン情報（ID・パスワード）はスクリプト内にハードコード禁止
- 個人情報（マイナンバー・口座番号）はいかなるファイルにも記載しない
- Playwright を使う場合は headless=False で動作確認してから headless 化
- 並列収集（Subagents）に対応できる設計にすること

---
