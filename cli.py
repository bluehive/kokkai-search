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
  --all             全件取得（100件ずつページング。リクエスト間隔は3秒以上）
  --max-total N     --all 時の取得上限
  --page-sleep SEC  ページ間スリープ（下限 3 秒）
  --jsonl PATH      JSONL 出力（ディレクトリならファイル名を自動生成）
  --outdir DIR      MD の出力先ディレクトリ
  --json            JSONのみ出力（MDは作成）
  --html            HTMLレポートファイルを生成（バッチPDF変換用）
  --browser-pdf     ブラウザでPDF用レポートを開く（印刷でPDF保存）

使い方例:
  python cli.py --query "生成AI 規制" --limit 5
  python cli.py --or-query "生成AI 規制" -o
  python cli.py --speaker "岸田" --from 2024-01-01
  python cli.py --meeting "予算委員会" --limit 3 --html
  python cli.py --query "生成AI" --browser-pdf
  python cli.py --query "安保" --speaker "岸信介" --all --jsonl out/ --outdir out
"""
import argparse
import datetime
import json
import os
import re
import sys
from kokkai_client import (
    KOKKAI_API_BASE,
    MIN_PAGE_SLEEP,
    search_speeches,
    search_speeches_all,
    get_meeting,
)

# 同ディレクトリのモジュールを確実にインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kokkai_report


JSONL_FIELDS = (
    "speechID",
    "issueID",
    "date",
    "nameOfHouse",
    "nameOfMeeting",
    "speaker",
    "speakerGroup",
    "speakerPosition",
    "speech",
    "speechURL",
    "meetingURL",
)


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


def resolve_jsonl_path(path: str, search_params: dict) -> str:
    """PATH がディレクトリ（既存、または末尾が /）なら自動ファイル名を付ける。"""
    if path.endswith("/") or path.endswith(os.sep) or os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
        name = kokkai_report.build_output_basename(search_params, ".jsonl")
        return os.path.join(path, name)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


def write_jsonl(path: str, items, search_params: dict) -> str:
    """1行1 JSON。検索条件を各行に添える。"""
    path = resolve_jsonl_path(path, search_params)
    with open(path, "w", encoding="utf-8") as fp:
        for item in items:
            row = {key: item.get(key) for key in JSONL_FIELDS}
            row["query"] = search_params.get("query")
            row["or"] = bool(search_params.get("or"))
            row["speaker_filter"] = search_params.get("speaker")
            row["from"] = search_params.get("from")
            row["until"] = search_params.get("until")
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def meta_path_for(jsonl_path: str) -> str:
    if jsonl_path.endswith(".jsonl"):
        return jsonl_path[: -len(".jsonl")] + ".meta.json"
    return jsonl_path + ".meta.json"


def write_meta(jsonl_path: str, search_params: dict, result: dict, page_sleep: float) -> str:
    meta = {
        "query": search_params.get("query"),
        "or": bool(search_params.get("or")),
        "speaker_filter": search_params.get("speaker"),
        "nameOfMeeting": search_params.get("nameOfMeeting"),
        "from": search_params.get("from"),
        "until": search_params.get("until"),
        "total_hits": result.get("total"),
        "total_hits_upper_bound": result.get("total_upper_bound"),
        "total_is_exact": bool(result.get("total_is_exact", not search_params.get("or"))),
        "fetched": result.get("fetched", len(result.get("items") or [])),
        "truncated": bool(result.get("truncated")),
        "requests": result.get("requests"),
        "page_size": 100 if search_params.get("fetch_all") else search_params.get("limit"),
        "page_sleep": page_sleep,
        "max_total": search_params.get("max_total"),
        "fetched_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "api_base": KOKKAI_API_BASE,
        "per_keyword_totals": result.get("per_keyword_totals"),
    }
    path = meta_path_for(jsonl_path)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="国会議事録検索 CLI (kokkai-mcp ベース)")
    parser.add_argument("--query", "-q", help="本文検索キーワード (AND検索)")
    parser.add_argument("--or-query", "-o", dest="or_query", help="本文検索キーワード (OR検索: いずれかのキーワードを含む)")
    parser.add_argument("--speaker", "-s", help="発言者名 (部分一致)")
    parser.add_argument("--meeting", "-m", dest="nameOfMeeting", help="会議名 (部分一致)")
    parser.add_argument("--from", dest="from_date", help="開始日 (YYYY-MM-DD または 1989年11月01日 のような形式)")
    parser.add_argument("--until", dest="until_date", help="終了日 (YYYY-MM-DD または 1989年11月01日まで のような形式)")
    parser.add_argument("--limit", "-n", type=int, default=10, help="取得件数 (最大100)。--all 指定時は無視")
    parser.add_argument("--all", action="store_true", help="全件取得（100件ずつページング）")
    parser.add_argument("--max-total", type=int, default=None, help="--all 時の取得件数の上限")
    parser.add_argument("--page-sleep", type=float, default=3.0, help="ページ間スリープ秒（下限 3）")
    parser.add_argument("--jsonl", help="JSONL 出力先。ディレクトリならファイル名を自動生成")
    parser.add_argument("--outdir", help="MD ファイルの出力先ディレクトリ（省略時はカレント）")
    parser.add_argument("--full", action="store_true", help="最初に見つかった会議録全体を表示")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    parser.add_argument("--html", action="store_true",
                        help="HTMLレポートファイルを生成（バッチPDF変換用）")
    parser.add_argument("--browser-pdf", action="store_true",
                        help="ブラウザでPDF用レポートを開く（印刷→PDF保存）")

    args = parser.parse_args(argv)

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

    page_sleep = args.page_sleep
    if page_sleep < MIN_PAGE_SLEEP:
        print(
            f"警告: --page-sleep {page_sleep} は下限 {MIN_PAGE_SLEEP:.0f} 秒に引き上げます",
            file=sys.stderr,
        )
        page_sleep = MIN_PAGE_SLEEP

    if not any([args.query, args.or_query, args.speaker, args.nameOfMeeting]):
        parser.print_help()
        print("\nエラー: --query / --or-query / --speaker / --meeting のいずれかを指定してください", file=sys.stderr)
        sys.exit(1)

    effective_query = args.or_query if args.or_query else args.query
    or_search = bool(args.or_query)

    def progress(msg):
        print(msg, file=sys.stderr)

    try:
        if args.all:
            result = search_speeches_all(
                query=effective_query,
                speaker=args.speaker,
                nameOfMeeting=args.nameOfMeeting,
                from_date=args.from_date,
                until_date=args.until_date,
                or_search=or_search,
                max_total=args.max_total,
                page_size=100,
                page_sleep=page_sleep,
                progress=progress,
            )
        else:
            result = search_speeches(
                query=effective_query,
                speaker=args.speaker,
                nameOfMeeting=args.nameOfMeeting,
                from_date=args.from_date,
                until_date=args.until_date,
                limit=args.limit,
                or_search=or_search,
            )
            result.setdefault("fetched", len(result.get("items") or []))
            total = result.get("total") or 0
            result.setdefault("truncated", result["fetched"] < int(total))
            result.setdefault("total_is_exact", not or_search)
            if "total_upper_bound" not in result and not or_search:
                result["total_upper_bound"] = int(total)
    except Exception as e:
        print(f"検索エラー: {e}", file=sys.stderr)
        sys.exit(1)

    fetched = result.get("fetched", len(result.get("items") or []))
    # 検索パラメータ（MD / PDF / JSONL 用）
    search_params = {
        "query": effective_query,
        "or": or_search,
        "speaker": args.speaker,
        "nameOfMeeting": args.nameOfMeeting,
        "from": args.from_date,
        "until": args.until_date,
        "limit": args.limit,
        "fetch_all": bool(args.all),
        "max_total": args.max_total,
        "fetched": fetched,
        "truncated": bool(result.get("truncated")),
        "total_is_exact": bool(result.get("total_is_exact", not or_search)),
        "total_upper_bound": result.get("total_upper_bound"),
    }

    # === 標準で MD ファイルを作成 ===
    try:
        md_path = kokkai_report.create_md_file(
            result["items"],
            search_params,
            total=result.get("total"),
            outdir=args.outdir,
        )
        print(f"\n📝 MDファイルを作成しました: {md_path}")
    except Exception as e:
        print(f"MDファイル作成失敗: {e}", file=sys.stderr)

    if args.jsonl:
        try:
            jsonl_path = write_jsonl(args.jsonl, result["items"], search_params)
            meta_path = write_meta(jsonl_path, search_params, result, page_sleep)
            print(f"JSONLを作成しました: {jsonl_path}")
            print(f"メタ情報を作成しました: {meta_path}")
        except Exception as e:
            print(f"JSONL作成失敗: {e}", file=sys.stderr)
            sys.exit(1)

    # HTML生成（バッチ向け）
    if args.html:
        try:
            html_path = kokkai_report.create_html_file(
                result["items"],
                search_params,
                total=result.get("total")
            )
            print(f"📄 HTMLファイルを作成しました: {html_path}")
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
