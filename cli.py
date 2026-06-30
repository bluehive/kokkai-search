#!/usr/bin/env python3
"""
Kokkai 検索 CLI (kokkai-mcp 互換の検索)
使い方例:
  python cli.py --query "生成AI" --limit 5
  python cli.py --speaker "岸田" --from 2024-01-01
  python cli.py --meeting "予算委員会" --limit 3
"""
import argparse
import json
import sys
from kokkai_client import search_speeches, get_meeting


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
    parser.add_argument("--query", "-q", help="本文検索キーワード (AND)")
    parser.add_argument("--speaker", "-s", help="発言者名 (部分一致)")
    parser.add_argument("--meeting", "-m", dest="nameOfMeeting", help="会議名 (部分一致)")
    parser.add_argument("--from", dest="from_date", help="開始日 YYYY-MM-DD")
    parser.add_argument("--until", dest="until_date", help="終了日 YYYY-MM-DD")
    parser.add_argument("--limit", "-n", type=int, default=10, help="取得件数 (最大100)")
    parser.add_argument("--full", action="store_true", help="最初に見つかった会議録全体を表示")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    if not any([args.query, args.speaker, args.nameOfMeeting]):
        parser.print_help()
        print("\nエラー: --query / --speaker / --meeting のいずれかを指定してください", file=sys.stderr)
        sys.exit(1)

    try:
        result = search_speeches(
            query=args.query,
            speaker=args.speaker,
            nameOfMeeting=args.nameOfMeeting,
            from_date=args.from_date,
            until_date=args.until_date,
            limit=args.limit,
        )
    except Exception as e:
        print(f"検索エラー: {e}", file=sys.stderr)
        sys.exit(1)

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
            print(f"会議録取得失攷: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
