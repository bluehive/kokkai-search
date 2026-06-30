# 国会議事録検索システム (kokkai-search)

**Built with Grok** (xAI)

国会議事録検索システム - ブラウザで簡単に検索・全文表示・PDF出力可能

https://github.com/harutomo51/kokkai-mcp のコア機能を活用した検索システムです。

kokkai-mcp が提供する `search_speeches` / `get_meeting` と同等の機能を、**ブラウザUI** と **CLI** で簡単に利用できます。

## 特徴

- 国立国会図書館「国会議事録検索システムAPI」を直接使用
- キーワード・発言者・会議名・期間で検索
- 検索結果から会議録全文をワンクリックで表示
- 依存なし（Python標準ライブラリのみ）
- kokkai-mcp と同じ検索ロジック

## 使い方

### 1. Web UI（おすすめ）

```bash
cd kokkai-search
python server.py
```

ブラウザで **http://localhost:8765** を開いてください。

- 検索フォームに入力して「検索」
- 結果カードをクリック → その会議の全発言を表示（モーダル）
- ページネーション対応

### 2. CLI

```bash
# 基本検索
python cli.py --query "生成AI" --limit 5

# 発言者指定
python cli.py -s "岸田" --from 2024-01-01 --limit 10

# 会議名で絞る + 全文取得
python cli.py --meeting "予算委員会" --limit 3 --full

# JSON出力
python cli.py -q "デジタル" --json
```

### 3. Python から使う（ライブラリ）

```python
from kokkai_client import search_speeches, get_meeting

# 検索
result = search_speeches(query="生成AI", limit=5, from_date="2025-01-01")
for item in result["items"]:
    print(item["speaker"], item["date"])

# 会議録全文
meeting = get_meeting("122114324X00520260610")
print(len(meeting["speeches"]), "件の発言")
```

## kokkai-mcp との関係

このシステムは **kokkai-mcp の検索部分を再利用・ラップ** したものです。

| 機能               | kokkai-mcp          | 本システム             |
|--------------------|---------------------|------------------------|
| 発言検索           | search_speeches     | ✓ (cli / web / lib)    |
| 会議録取得         | get_meeting         | ✓                      |
| AI要約             | summarize_*         | ✗ (要Claude API)       |
| 時系列/政党比較    | compare_* / analyze | ✗                      |

**高度な要約・分析** をしたい場合は、kokkai-mcp を Claude Desktop や MCP対応クライアントで併用してください。

## 技術メモ

- 使用API: `https://kokkai.ndl.go.jp/api/speech` および `/meeting`
- 利用規約: [国会議事録検索システム利用規約](https://kokkai.ndl.go.jp/terms.html) に従ってください
- キャッシュ: 実装していません（必要なら追加可能）
- サーバーはローカルプロキシとして動作するため、ブラウザからの直接CORS問題を回避

## 開発 / 拡張アイデア

- キャッシュの追加（メモリ or SQLite）
- 要約機能の追加（Anthropic APIキー使用）
- ページネーションの改善
- 結果のCSV/JSONエクスポート
- MCPサーバーとしてこの検索を公開

---

kokkai-mcp 作者に感謝。
この検索システムは同APIラッパーをベースにしています。

## トラブルシューティング

### 「Firefox が localhost:8765 のサーバーに接続できません」

1. **サーバーが本当に起動しているか確認**
   ```powershell
   cd C:\Users\mevius\Documents\my-project\kokkai-search
   python server.py
   ```
   起動すると以下のようなメッセージが出ます：
   ```
   ✅ 国会議事録検索システム サーバー起動完了
   ブラウザで以下のどちらかを開いてください:
      http://localhost:8765
      http://127.0.0.1:8765
   ```

2. **正しいURLを試す**
   - `http://localhost:8765` ではなく **`http://127.0.0.1:8765`** を試してください
   - アドレスバーに直接入力（コピー＆ペースト推奨）

3. **ディレクトリが正しいか**
   必ず `kokkai-search` フォルダの中で `python server.py` を実行。

4. **ポートが使われていないか**
   ```powershell
   netstat -ano | findstr :8765
   ```
   何か出ていたら他のプロセスが使っています。`python server.py 9000` で別ポートで起動できます。

5. **Pythonのバージョン確認**
   ```powershell
   python --version
   ```
   Python 3.8 以上が推奨。

6. **他のブラウザで試す**
   Microsoft Edge や Chrome で `http://127.0.0.1:8765` を開いてみてください。

7. **ファイアウォール**
   稀にWindows Defenderがブロックしますが、localhostの場合は通常問題になりません。
   それでもダメなら一旦「プライベートネットワーク」で許可してみてください。

### サーバーがすぐに終了する
古いバージョンの `server.py` を使っている可能性があります。
最新のコード（`if __name__ == "__main__":` ブロックがあるもの）に更新してください。

## License

MIT License

Copyright (c) 2026 bluehive

Built with Grok by xAI.

See the [LICENSE](LICENSE) file for details.