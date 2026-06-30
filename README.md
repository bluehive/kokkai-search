# 国会議事録検索システム (kokkai-search)

**Built with Grok** (xAI)

国会議事録検索システム - ブラウザで簡単に検索・全文表示・PDF出力可能

https://github.com/harutomo51/kokkai-mcp のコア機能を活用した検索システムです。

kokkai-mcp が提供する `search_speeches` / `get_meeting` と同等の機能を、**ブラウザUI** と **CLI** で簡単に利用できます。

## 特徴

- 国立国会図書館「国会会議録検索システムAPI」を直接使用
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

CLIは画面表示に加え、**標準でMarkdownファイルを作成**します。

**ファイル名規則**（現在のディレクトリに作成）:
`YYYYMMDD-クエリ-発言者-from.md`

例: `20240630-生成AI-岸田-2024-01-01.md`

**検索モード**:

- `--query "kw1 kw2"` (または `-q`) : **AND検索**（すべてのキーワードを含む、デフォルト）
- `--or-query "kw1 kw2"` (または `-o`) : **OR検索**（いずれかのキーワードを含む）

```bash
# AND検索（MDファイル自動作成）
python cli.py --query "生成AI 規制" --limit 5

# OR検索
python cli.py --or-query "生成AI 規制" -o

# 発言者 + 期間指定
python cli.py -s "岸田" --from 2024-01-01 --limit 10

# ブラウザでPDFレポートを開く（印刷 → PDF保存）
python cli.py --query "生成AI" --browser-pdf
```

**主なオプション**:

- `--query` / `-q` : 本文検索キーワード (AND検索、デフォルト)
- `--or-query` / `-o` : 本文検索キーワード (OR検索)
- `--json` : JSON出力のみ（MD作成はスキップ）
- `--html` : HTMLレポートファイルを生成（バッチ処理・PDF変換用）
- `--browser-pdf` : ブラウザでPDF用レポートを開く（印刷ダイアログでPDF保存）
- `--full` : 最初にヒットした会議録の全文を表示

**複数クエリの一括処理例（テキストファイル + bash）**:

```bash
# queries.txt の例（1行1クエリ）
# query speaker from
生成AI 上野 2024-01-01
デジタル 岸田 2023-01-01

# 一括実行（MD + HTMLを自動生成）。OR検索も可能
while read q s f; do
  python cli.py --query "$q" -s "$s" --from "$f" --html
  # OR検索例: python cli.py --or-query "$q" -o -s "$s" --from "$f" --html
done < queries.txt
```

生成された .html ファイルを一括でPDFに変換したい場合は、外部ツール（wkhtmltopdfなど）と組み合わせることをおすすめします（Python標準ライブラリのみでは高品質PDFの直接生成は実用的には困難です）。

**Pythonモジュール (kokkai_report.py)**:

```python
import kokkai_report

# MDファイル作成
md_path = kokkai_report.create_md_file(items, params, total=...)

# ブラウザでPDFレポートを開く
kokkai_report.open_in_browser_for_pdf(items, params)
```

### バッチ処理（複数クエリの一括実行）

テキストファイルに複数クエリを用意して一括処理するためのヘルパースクリプト `kokkai_batch.py` を用意しています。

**queries.txt の例**（リポジトリに `queries.txt` サンプルも同梱）:

```
# コメントは # で始められます
--query "生成AI" --speaker "岸田" --from "2024-01-01"
--or-query "デジタル 規制" -o -s "上野" --from "1989年11月01日まで"
--query "AI規制" --from "2023年" --until "2025年12月31日"
```

**基本実行**:

```bash
python kokkai_batch.py queries.txt
```

**拡張オプション例**:

```bash
# 並列2実行 + ログ出力 + スリープ調整 + リトライ + ドライラン
# OR検索もサポート
python kokkai_batch.py queries.txt \
  --workers 2 \
  --log-file batch.log \
  --sleep-min 1 \
  --sleep-max 5 \
  --retry 2 \
  --dry-run
```

**主なオプション**:

- `--workers N` : 並列実行数（デフォルト: 1）。API負荷に注意して使用してください。
- `--log-file FILE` : 実行ログをファイルに出力。
- `--sleep-min` / `--sleep-max` : クエリ間のスリープ秒を調整（デフォルト 1〜5秒）。
- `--retry N` : 失敗時のリトライ回数（デフォルト: 0）。
- `--dry-run` : 実際に実行せず、予定のコマンドのみ表示。

**追加機能**:
- シンプルな進捗バー表示（% と バー）。
- 実行終了時に成功/失敗件数サマリー。
- 失敗時は指数バックオフでリトライ。

- 各クエリごとに MD ファイルが自動生成されます。
- API サーバー負荷を避けるため、**クエリごとにランダムスリープ** を入れています。
- `--from` / `--until` は通常の `YYYY-MM-DD` に加え、 **「1989年11月01日まで」** のような日本語表記もサポートしています。

サンプルファイル `queries.txt` がリポジトリに含まれています。適宜編集してご利用ください。

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

**レポート生成 (kokkai_report)**:

```python
import kokkai_report

# MD作成
kokkai_report.create_md_file(result["items"], params, total=result["total"])

# ブラウザでPDFレポートを開く
kokkai_report.open_in_browser_for_pdf(result["items"], params)
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
- 利用規約: [国会会議録検索システム利用規約](https://kokkai.ndl.go.jp/terms.html) に従ってください
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