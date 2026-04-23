# agent-skills-money-ops

確定申告・クレカ明細・ポイント管理などの個人財務業務を自動化する Claude Agent Skills プロジェクト。

## セットアップ

### 前提

- Claude Code インストール済み
- Python 3.11+
- 依存パッケージ: `pip install -r requirements.txt`

### スキル認識の設定（初回のみ）

Claude Code がプロジェクト内の `skills/` を認識するため、`.claude/skills` → `skills/` のジャンクションを作成する。

**管理者権限の cmd で実行（プロジェクトルートで）:**

```cmd
mklink /J .claude\skills skills
```

作成後、Claude Code を再起動するとスキルが認識される。
