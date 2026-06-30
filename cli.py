#!/usr/bin/env python3
"""
Kokkai 検索 CLI (kokkai-mcp 互換の検索)

標準動作:
- 画面表示
- MDファイル自動作成（現在のディレクトリ）
  ファイル名: YYYYMMDD-クエリ-発言者-from.md

検索モード:
  --query "kw1 kw2"          : AND検索 (すべて含む、デフォルト)
  --or-query "kw1 kw2" -o    : OR検索 (いずれかを含む)

追加オプション:
  --json            JSONのみ出力（MDは作成）
  --html            HTMLレポートファイルを生成（バッチPDF変換用）
  --browser-pdf     ブラウザでPDF用レポートを開く（印刷でPDF保存）

使い方例:
  python cli.py --query "生成AI 規制" --limit 5
  python cli.py --or-query "生成AI 規制" -o
  python cli.py --speaker "岸田" --from 2024-01-01
  python cli.py --meeting "予算委員会" --limit 3 --html
  python cli.py --query "生成AI" --browser-pdf
"""
import argparse
import datetime
import json
import os
import re
import sys
from kokkai_client import search_speeches, get_meeting

# 同ディレクトリのモジュールを確実にインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kokkai_report


def print_speech(item: dict, idx: int = None):
    prefix = f"[{idx}] " if idx is not None else ""
    print(f"{prefix}{item.get('date', '?')} | {item.get('speaker', '?')}")
    meeting = item.get('nameOfMeeting') or ""
    if meeting:
        print(f"    会議: {meeting}")
    speech = (item.get("speech") or "").replace("\r\n", " ").replace("\n", " ")
    print(f"    {speech[:160]}{'...' if len(speech) > 160 else ''}")
    if item.get("speechURL"):
        print(f"    発言URL: {item['speechURL']}")
    if item.get("issueID"):
        print(f"    issueID: {item['issueID']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="国会議事録検索 CLI (kokkai-mcp ベース)")
    parser.add_argument("--query", "-q", help="本文検索キーワード (AND検索)")
    parser.add_argument("--or-query", "-o", dest="or_query", help="本文検索キーワード (OR検索: いずれかのキーワードを含む)")
    parser.add_argument("--speaker", "-s", help="発言者名 (部分一致)")
    parser.add_argument("--meeting", "-m", dest="nameOfMeeting", help="会議名 (部分一致)")
    parser.add_argument("--from", dest="from_date", help="開始日 (YYYY-MM-DD または 1989年11月01日 のような形式)")
    parser.add_argument("--until", dest="until_date", help="終了日 (YYYY-MM-DD または 1989年11月01日まで のような形式)")
    parser.add_argument("--limit", "-n", type=int, default=10, help="取得件数 (最大100)")
    parser.add_argument("--full", action="store_true", help="最初に見つかった会議録全体を表示")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--html", action="store_true", 
                        help="HTMLレポートファイルを生成（バッチPDF変換用）")
    parser.add_argument("--browser-pdf", action="store_true", 
                        help="ブラウザでPDF用レポートを開く（印刷→PDF保存）")

    args = parser.parse_args()

    def normalize_date(d):
        if not d:
            return None
        d = str(d).strip()
        # Strip Japanese qualifiers like まで, から
        d = re.sub(r'(まで|から|以降|以前|以後)', '', d).strip()
        # Japanese format: 1989年11月01日
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日?', d)
        if match:
            y, m, dd = match.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(dd):02d}"
        # Validate standard format
        try:
            datetime.datetime.strptime(d, "%Y-%m-%d")
            return d
        except ValueError:
            return d  # let it fail later if invalid

    args.from_date = normalize_date(args.from_date)
    args.until_date = normalize_date(args.until_date)

    if not any([args.query, args.or_query, args.speaker, args.nameOfMeeting]):
        parser.print_help()
        print("\nエラー: --query / --or-query / --speaker / --meeting のいずれかを指定してください", file=sys.stderr)
        sys.exit(1)

    try:
        effective_query = args.or_query if args.or_query else args.query
        or_search = bool(args.or_query)
        result = search_speeches(
            query=effective_query,
            speaker=args.speaker,
            nameOfMeeting=args.nameOfMeeting,
            from_date=args.from_date,
            until_date=args.until_date,
            limit=args.limit,
            or_search=or_search,
        )
    except Exception as e:
        print(f"検索エラー: {e}", file=sys.stderr)
        sys.exit(1)

    # 検索パラメータ（MD / PDF用）
    search_params = {
        "query": effective_query,
        "or": or_search,
        "speaker": args.speaker,
        "nameOfMeeting": args.nameOfMeeting,
        "from": args.from_date,
        "until": args.until_date,
        "limit": args.limit,
    }

    # === 標準で MD ファイルを作成 ===
    try:
        md_path = kokkai_report.create_md_file(
            result["items"], 
            search_params, 
            total=result.get("total")
        )
        print(f"\n\uD83D\uDCDD MDファイルを作成しました: {md_path}")
    except Exception as e:
        print(f"MDファイル作成失敗: {e}", file=sys.stderr)

    # HTML生成（バッチ向け）
    if args.html:
        try:
            html_path = kokkai_report.create_html_file(
                result["items"], 
                search_params, 
                total=result.get("total")
            )
            print(f"\uD83D\uDCC4 HTMLファイルを作成しました: {html_path}")
            print("   このファイルをブラウザや外部ツールでPDFに変換してください。")
        except Exception as e:
            print(f"HTMLファイル作成失敗: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"検索結果: {result['total']} 件 (表示 {len(result['items'])} 件)")
    print("=" * 60)
    for i, item in enumerate(result["items"], 1):
        print_speech(item, i)

    if args.full and result["items"]:
        issue_id = result["items"][0]["issueID"]
        print(f"\n=== 会議録全文取得 (issueID={issue_id}) ===")
        try:
            meeting = get_meeting(issue_id)
            print(f"{meeting['date']} {meeting['nameOfMeeting']}")
            print(f"発言数: {len(meeting['speeches'])}")
            print("-" * 60)
            for sp in meeting["speeches"][:30]:  # 長くなりすぎ防止
                print_speech(sp)
            if len(meeting["speeches"]) > 30:
                print(f"... 他 {len(meeting['speeches']) - 30} 件 (省略)")
        except Exception as e:
            print(f"会議録取得失敗: {e}", file=sys.stderr)

    # === おまけ: ブラウザでPDFレポートを開く ===
    if args.browser_pdf:
        try:
            kokkai_report.open_in_browser_for_pdf(
                result["items"], 
                search_params, 
                total=result.get("total")
            )
        except Exception as e:
            print(f"ブラウザPDFオープン失敗: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
