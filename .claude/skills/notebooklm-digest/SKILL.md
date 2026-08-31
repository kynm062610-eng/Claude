---
name: notebooklm-digest
description: Use when the user wants to bring research or notes they created in Google NotebookLM into Claude Code for analysis, discussion, or further writing. Triggers on "NotebookLM", "ノートブックLM", "NotebookLMの要約", exported notebook guides/briefing docs, or a request to read/summarize a NotebookLM export sitting in Google Drive.
---

# NotebookLM 連携（役割分担ワークフロー）

情報の大量読み込み（体力勝負のリサーチ）は NotebookLM に任せ、要約されたアウトプットを
Claude Code に読ませて考察・執筆・意思決定に使う、という役割分担を実行するためのスキル。

NotebookLM には公式 API / MCP 連携が存在しないため、完全自動化はできない。
「NotebookLM → Google ドキュメントへエクスポート → Google Drive → Claude Code が読む」
という手動ブリッジを使う。

## 前提

- Google Drive connector が有効であること（`mcp__*__search_files` /
  `mcp__*__read_file_content` 系のツールが使えるか `ListConnectors` で確認する）。
  未接続なら、claude.ai のコネクタ設定で Google Drive を接続するようユーザーに伝える。

## ユーザー側の手順（毎回これをやってもらう）

1. NotebookLM で調べたいソース（PDF・URL・文書など）を読み込ませる。
2. 右側の Studio パネルで「ノートブック ガイド」「概要」または個別メモを開く。
3. 「Google ドキュメントにエクスポート」を実行する（ノートブックごと・メモごとに可能）。
   これで要約が Google Drive 上の Doc として保存される。

## Claude Code 側の手順

1. Google Drive connector の検索ツールで、直近作成された対象ドキュメントを探す
   （ファイル名にキーワードが入っていない場合は、直近更新順で候補を出してユーザーに確認する）。
2. 該当ファイルの内容を読み込む。
3. ユーザーが求める作業を行う。例:
   - 複数ソースの要約を横断して矛盾点・共通点を洗い出す
   - 要約を元に構成案・記事・スライド構成を作る
   - 不足している論点や、裏取りが必要な主張を指摘する
4. 出力は Claude Code 側の成果物（ドキュメント、コード、artifact など）として渡す。
   NotebookLM 側には書き戻さない。

## 注意点

- NotebookLM の要約はソースの誤読・幻覚を含みうる。重要な数値や引用は、可能なら元ソースに
  当たって裏取りする一言を添える。
- ドキュメントが長大な場合、関連セクションだけを抜粋して渡すよう促すとコンテキストを節約できる。
