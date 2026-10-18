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
- `--all` : 全件取得（100件ずつページング。リクエスト間隔は3秒以上）
- `--max-total N` : `--all` の取得上限
- `--page-sleep SEC` : ページ間スリープ（下限 3 秒）
- `--jsonl PATH` : JSONL 出力。ディレクトリならファイル名を自動生成し、`.meta.json` も書く
- `--outdir DIR` : MD の出力先（省略時はカレントディレクトリ）
- `--json` : 結果を JSON でも標準出力する（MD は作成する）
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

## 全件取得（ページング）と JSONL 出力

`--limit` の既定は 10 件です。API の `maximumRecords` は最大 100 なので、ヒットがそれより多いときは `--all` でページをたどります。ページの位置は `startRecord` と応答の `nextRecordPosition` で進め、`nextRecordPosition` が無い、0 件のページが返る、または `--max-total` に達したところで止まります。

```bash
# 全件（100件ずつ）。MD は --outdir、JSONL はディレクトリ指定で自動命名
python cli.py --or-query "全学連 集団的暴力 法秩序" \
  --speaker "岸信介" --from 1960-05-01 --until 1960-07-31 \
  --all --jsonl out/ --outdir out

# 多くても 50 件で打ち切る（NDL の any はスペース区切りが AND なので、広い語で取る）
python cli.py --query "安保" --speaker "岸信介" --all --max-total 50 --jsonl out/
```

- `--all` : 100 件ずつ全ページを取得する。指定しないときの挙動（既定 `--limit 10`、MD を作る）は変わりません。
- `--max-total N` : `--all` の取得件数の上限。超えた分は取りません。
- `--page-sleep SEC` : リクエストのあいだに待つ秒数。既定 3。3 未満は警告して 3 秒に引き上げます。最初のリクエストの前には待ちません。
- `--jsonl PATH` : 1 行 1 JSON（UTF-8、日本語はそのまま）で書きます。PATH がディレクトリ、または末尾が `/` のときは、MD と同じ規則のファイル名（拡張子 `.jsonl`）をその中に作ります。各行には `speechID` などの発言フィールドに加え、`query` / `or` / `speaker_filter` / `from` / `until` を付けます。
- `--outdir DIR` : MD の出力先。省略すると今までどおりカレントディレクトリです。

JSONL と対になる `<名前>.meta.json` に、検索条件、`total_hits`（総ヒット数）、`total_hits_upper_bound`、`total_is_exact`、`fetched`（取得件数）、`truncated`、リクエスト回数、`page_size`、`page_sleep`、`fetched_at`、`api_base` を書きます。OR 検索ではキーワードごとの `numberOfRecords` を `per_keyword_totals` に残します。

NDL API の `any` はスペース区切りで AND 検索になります。OR は本ツールの `--or-query` がキーワードごとに検索し、`speechID` で重複除去します。キーワード間で同じ発言が重複しうるため、全ページを取り切ったときの OR の総ヒット数はユニーク件数です（`total_is_exact` が真）。途中で打ち切ったときはユニーク総数が分からないので、`total_hits` は取得件数のまま、`total_is_exact` は偽、`total_hits_upper_bound` はキーワード別合計（重複を含む上限）です。非 OR では API の `numberOfRecords` が総ヒット数なので、打ち切っても `total_is_exact` は真です。

全ページを取り切れていないときは `truncated` が真になり、MD の見出しにも次の行が出ます。

- `- 総ヒット数: N`（非 OR、または OR で全ページを取り切ったとき）
- `- 総ヒット数: 不明（キーワード別合計の上限 N）`（OR で打ち切ったとき。ユニーク総数は出さない）
- `- 取得件数: M`
- `- ⚠ 取得件数が総ヒット数より少ない（切り詰め）`（総ヒット数が分かっていて切り詰めたときだけ）

`--all` のときの「取得上限」は `全件 (--all)`、`--max-total` があるときはその上限です。

国会会議録 API への依頼は、どの依頼のあいだも 3 秒以上空け、同時実行は 1 本（`workers=1`）にしてください。`kokkai_batch.py` はクエリのあいだに `--sleep-min`〜`--sleep-max` 秒（既定 3〜5、下限 3）待ちます。最後のクエリの後は待ちません。`--workers` が 1 より大きいときは警告します。バッチ行の `{outdir}` は `--outdir` の値に置き換わり、出力先ディレクトリは無ければ作ります。

ジャパニズム分析用のクエリは `japanism_queries.txt` にあります。NDL の `any` はスペース区切りが AND なので、狭い AND（例: 「安保 改定」は 89 件）ではなく、確認済みの広い語と `--or-query` を使います。推定リクエスト数は約 20（1 リクエスト 100 件以下、間隔 3 秒以上）で、所要は約 2〜3 分です。件数は NDL API で確認した値です。

| 行 | 検索 | 確認件数 |
| --- | --- | --- |
| 岸信介 × `共産` | AND（単一語） | 243（共産主義 155・共産党 22 を含む上位集合） |
| 中曽根康弘 × `共産` | AND（単一語） | 266（共産主義 34・共産党 177） |
| 岸信介 × `安保`（1960-01-01〜07-31） | AND（単一語） | 338（「安保 改定」の AND だと 89） |
| 岸信介 × `全学連 集団的暴力 法秩序`（1960-05-01〜07-31） | OR（speechID で重複除去） | 全学連 2・集団的暴力 5・法秩序 6 |
| 佐藤栄作 × `三島 市ヶ谷`（1970-11-25〜12-31） | OR | 三島 6・市ヶ谷 若干（「佐藤」だと他の佐藤議員が混ざり三島 12） |
| 安倍晋三 × `平和安全法制 集団的自衛権`（2015-05-01〜10-01） | OR | 平和安全法制 140・集団的自衛権 230 |

岸信介との対比用に、吉田茂の首相期（1947-05-20〜1954-12-10、旧安保期だけ 1951-09-01〜1952-04-28）を `japanism_yoshida_queries.txt` に分けています。発言者「吉田茂」は同名が 2005 年に現れるため、どの行も `--from` と `--until` で日付を区切ります。推定リクエスト数は約 11（間隔 3 秒以上）で、所要は約 1〜1.5 分です。

| 行 | 検索 | 確認件数 |
| --- | --- | --- |
| Y1 吉田茂 × `共産`（1947-05-20〜1954-12-10） | AND（単一語） | 221 |
| Y2 吉田茂 × `安保 安全保障条約`（1951-09-01〜1952-04-28） | OR（speechID で重複除去） | 安全保障条約 105・安保 8 |
| Y3 吉田茂 × `再軍備`（1947-05-20〜1954-12-10） | AND（単一語） | 255（岸信介は全期間 5） |
| Y4 吉田茂 × `自由主義 経済復興`（1947-05-20〜1954-12-10） | OR | 自由主義 32・経済復興 23 |

```bash
mise run test                       # オフラインの単体テスト
mise run fetch:japanism:dry         # API を叩かず、置換後のコマンドだけ表示
mise run fetch:japanism             # 実取得。出力先は KOKKAI_OUT
mise run fetch:japanism:yoshida:dry # 吉田茂バッチのドライラン（API は叩かない。推定 ≈ 11 リクエスト）
mise run fetch:japanism:yoshida     # 吉田茂を実取得（API を叩く。推定 ≈ 11 リクエスト、所要 ≈ 1–1.5 分）
```

`KOKKAI_OUT` が未設定なら `~/my-project/mypublish-japanism/notes/japanism-tasogare/kokkai-analysis/cache` を使います。実行前に別のディレクトリを渡すとそちらが優先されます。`mise run smoke` は全学連×岸信介（1960-01-01〜12-31）の疎通確認で、想定は 5 件・1 リクエストです。`mise run smoke:paging` は共産×岸信介を `--max-total 150` で打ち切り、2 ページ（150 件取得、`truncated`、`total_hits` 243）になることの確認です。どちらも API を叩くので、通常は実行しません。

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
# 逐次実行 + ログ出力 + スリープ調整 + リトライ + ドライラン
# OR検索もサポート。workers は 1 を推奨
python kokkai_batch.py queries.txt \
  --workers 1 \
  --log-file batch.log \
  --sleep-min 3 \
  --sleep-max 5 \
  --retry 2 \
  --outdir out \
  --dry-run
```

**主なオプション**:

- `--workers N` : 並列実行数（デフォルト: 1）。1 より大きいと警告します。礼儀として 1 を推奨します。
- `--log-file FILE` : 実行ログをファイルに出力。
- `--sleep-min` / `--sleep-max` : クエリ間のスリープ秒（デフォルト 3〜5秒）。3 未満は 3 秒に引き上げます。最後のクエリの後は待ちません。
- `--outdir DIR` : 出力先。バッチ行の `{outdir}` をこのパスに置換し、ディレクトリが無ければ作ります。
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