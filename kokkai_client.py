#!/usr/bin/env python3
"""
Kokkai API クライアント (stdlib のみ)
kokkai-mcp の search_speeches / get_meeting と同等の機能を提供。
"""
import json
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, List, Optional


KOKKAI_API_BASE = "https://kokkai.ndl.go.jp/api"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RECORDS = 30
MIN_PAGE_SLEEP = 3.0


def _build_url(endpoint: str, params: Dict[str, Any]) -> str:
    """検索パラメータからURLを構築"""
    query = {}
    if params.get("query"):
        query["any"] = params["query"]
    if params.get("speaker"):
        query["speaker"] = params["speaker"]
    if params.get("nameOfMeeting"):
        query["nameOfMeeting"] = params["nameOfMeeting"]
    if params.get("from"):
        query["from"] = params["from"]
    if params.get("until"):
        query["until"] = params["until"]

    # 共通
    query["recordPacking"] = "json"
    max_rec = params.get("limit") or params.get("maximumRecords") or DEFAULT_MAX_RECORDS
    query["maximumRecords"] = str(min(int(max_rec), 100))

    start = params.get("startRecord") or 1
    query["startRecord"] = str(start)

    url = f"{KOKKAI_API_BASE}/{endpoint}"
    if query:
        url += "?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
    return url


def _fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """URLからJSONを取得（エラー処理付き）"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "kokkai-search/1.0 (https://github.com/)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            data = resp.read().decode(charset, errors="replace")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTPエラー {e.code}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"API接続エラー: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSONパースエラー: {e}") from e


def _record_to_item(rec: Dict[str, Any]) -> Dict[str, Any]:
    """speechRecord 1件を共通の item 辞書へ変換する。"""
    return {
        "speechID": rec.get("speechID"),
        "issueID": rec.get("issueID"),
        "date": rec.get("date"),
        "nameOfHouse": rec.get("nameOfHouse"),
        "nameOfMeeting": rec.get("nameOfMeeting"),
        "issue": rec.get("issue"),
        "speaker": rec.get("speaker", ""),
        "speakerGroup": rec.get("speakerGroup"),
        "speakerPosition": rec.get("speakerPosition"),
        "speakerRole": rec.get("speakerRole"),
        "speechOrder": rec.get("speechOrder"),
        "speech": rec.get("speech", ""),
        "speechURL": rec.get("speechURL"),
        "meetingURL": rec.get("meetingURL"),
    }


def _split_keywords(query: str) -> List[str]:
    keywords = [k.strip() for k in (query or "").split() if k.strip()]
    return keywords or ([query] if query else [])


def _page_one_query(
    query: Optional[str],
    speaker: Optional[str],
    nameOfMeeting: Optional[str],
    from_date: Optional[str],
    until_date: Optional[str],
    page_size: int,
    page_sleep: float,
    fetch: Callable[[str], Dict[str, Any]],
    sleep: Callable[[float], None],
    progress: Optional[Callable[..., None]],
    max_items: Optional[int],
    start_request_index: int = 0,
    progress_label: str = "",
) -> Dict[str, Any]:
    """1キーワード分を startRecord でページングして集める。

    sleep はリクエストのあいだだけ入れる（最初のリクエストの前には入れない）。
    max_items に達したらそこで打ち切る。
    """
    page_size = max(1, min(int(page_size), 100))
    sleep_sec = max(float(page_sleep), MIN_PAGE_SLEEP)
    items: List[Dict[str, Any]] = []
    requests = 0
    total = 0
    start = 1
    truncated = False

    while True:
        if requests > 0:
            sleep(sleep_sec)
        params = {
            "query": query,
            "speaker": speaker,
            "nameOfMeeting": nameOfMeeting,
            "from": from_date,
            "until": until_date,
            "limit": page_size,
            "startRecord": start,
        }
        url = _build_url("speech", params)
        data = fetch(url)
        requests += 1
        total = int(data.get("numberOfRecords") or 0)
        records = data.get("speechRecord") or []
        if not records:
            break

        for rec in records:
            items.append(_record_to_item(rec))
            if max_items is not None and len(items) >= max_items:
                truncated = True
                break

        page_no = start_request_index + requests
        if progress is not None:
            shown_total = total if total else len(items)
            label = f"{progress_label} " if progress_label else ""
            progress(f"{label}page {page_no}: {len(items)}/{shown_total}")

        if truncated:
            break
        next_pos = data.get("nextRecordPosition")
        if not next_pos:
            break
        start = int(next_pos)

    if max_items is not None and total > len(items):
        truncated = True
    return {
        "total": total,
        "items": items,
        "requests": requests,
        "truncated": truncated,
    }


def search_speeches(
    query: Optional[str] = None,
    speaker: Optional[str] = None,
    nameOfMeeting: Optional[str] = None,
    from_date: Optional[str] = None,
    until_date: Optional[str] = None,
    limit: int = 10,
    start: int = 1,
    or_search: bool = False,
    fetch: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    発言検索 (search_speeches 相当)
    or_search=True の場合、query のキーワードのいずれかを含む (OR検索)
    返り値: { total: int, items: list[SpeechItem], nextRecordPosition?: int }
    """
    if not any([query, speaker, nameOfMeeting]):
        raise ValueError("query, speaker, nameOfMeeting のいずれかを指定してください")

    do_fetch = fetch or _fetch_json

    if query and or_search:
        keywords = _split_keywords(query)
        items: List[Dict[str, Any]] = []
        seen = set()
        per_keyword_totals: Dict[str, int] = {}
        # limit<=100 はキーワードごとに1ページ。重複除去後に limit で切る。
        page_limit = min(max(int(limit), 1), 100)
        for kw in keywords:
            sub_params = {
                "query": kw,
                "speaker": speaker,
                "nameOfMeeting": nameOfMeeting,
                "from": from_date,
                "until": until_date,
                "limit": page_limit,
                "startRecord": start,
            }
            url = _build_url("speech", sub_params)
            data = do_fetch(url)
            per_keyword_totals[kw] = int(data.get("numberOfRecords") or 0)
            for rec in data.get("speechRecord", []) or []:
                item = _record_to_item(rec)
                sid = item.get("speechID")
                if sid in seen:
                    continue
                seen.add(sid)
                items.append(item)
        items = items[:limit]
        # OR の numberOfRecords はキーワード間で重複しうるので、
        # ユニーク件数を total とし、生のヒット数は per_keyword_totals に残す。
        # 1ページずつしか見ないので、重複をまたいだユニーク総数は確定しない。
        upper = sum(per_keyword_totals.values())
        result = {
            "total": len(items),
            "items": items,
            "per_keyword_totals": per_keyword_totals,
            "total_upper_bound": upper,
            "total_is_exact": False,
        }
        return result

    params = {
        "query": query,
        "speaker": speaker,
        "nameOfMeeting": nameOfMeeting,
        "from": from_date,
        "until": until_date,
        "limit": limit,
        "startRecord": start,
    }
    url = _build_url("speech", params)
    data = do_fetch(url)

    items = [_record_to_item(rec) for rec in (data.get("speechRecord") or [])]

    result = {
        "total": data.get("numberOfRecords", 0),
        "items": items,
        "total_is_exact": True,
        "total_upper_bound": int(data.get("numberOfRecords") or 0),
    }
    if data.get("nextRecordPosition"):
        result["nextRecordPosition"] = data["nextRecordPosition"]
    return result


def search_speeches_all(
    query: Optional[str] = None,
    speaker: Optional[str] = None,
    nameOfMeeting: Optional[str] = None,
    from_date: Optional[str] = None,
    until_date: Optional[str] = None,
    or_search: bool = False,
    max_total: Optional[int] = None,
    page_size: int = 100,
    page_sleep: float = 3.0,
    fetch: Optional[Callable[[str], Dict[str, Any]]] = None,
    sleep: Callable[[float], None] = time.sleep,
    progress: Optional[Callable[..., None]] = None,
) -> Dict[str, Any]:
    """全ページを startRecord でたどって発言を集める。

    リクエストのあいだは page_sleep 秒以上（下限 3 秒）待つ。
    返り値: {total, fetched, items, requests, truncated, per_keyword_totals?}
    """
    if not any([query, speaker, nameOfMeeting]):
        raise ValueError("query, speaker, nameOfMeeting のいずれかを指定してください")

    do_fetch = fetch or _fetch_json
    cap = None if max_total is None else max(int(max_total), 0)

    if query and or_search:
        return _search_speeches_all_or(
            keywords=_split_keywords(query),
            speaker=speaker,
            nameOfMeeting=nameOfMeeting,
            from_date=from_date,
            until_date=until_date,
            page_size=page_size,
            page_sleep=page_sleep,
            fetch=do_fetch,
            sleep=sleep,
            progress=progress,
            cap=cap,
        )

    page = _page_one_query(
        query=query,
        speaker=speaker,
        nameOfMeeting=nameOfMeeting,
        from_date=from_date,
        until_date=until_date,
        page_size=page_size,
        page_sleep=page_sleep,
        fetch=do_fetch,
        sleep=sleep,
        progress=progress,
        max_items=cap,
    )
    total = page["total"]
    return {
        "total": total,
        "fetched": len(page["items"]),
        "items": page["items"],
        "requests": page["requests"],
        "truncated": bool(page["truncated"] or (total > len(page["items"]))),
        # 非 OR の total は API の numberOfRecords。打ち切っても母数は分かる。
        "total_is_exact": True,
        "total_upper_bound": total,
    }


def _search_speeches_all_or(
    keywords: List[str],
    speaker: Optional[str],
    nameOfMeeting: Optional[str],
    from_date: Optional[str],
    until_date: Optional[str],
    page_size: int,
    page_sleep: float,
    fetch: Callable[[str], Dict[str, Any]],
    sleep: Callable[[float], None],
    progress: Optional[Callable[..., None]],
    cap: Optional[int],
) -> Dict[str, Any]:
    """OR 検索: キーワードごとに全ページを取り、speechID で重複除去する。

    リクエストのあいだ（キーワードをまたぐ間隔を含む）は必ず sleep する。
    全ページを取り切ったとき total はユニーク件数で total_is_exact=True。
    途中で打ち切ったときはユニーク総数が分からないので total は取得件数のまま、
    total_is_exact=False、total_upper_bound はキーワード別 numberOfRecords の
    合計（重複を含む上限）にする。
    """
    page_size = max(1, min(int(page_size), 100))
    sleep_sec = max(float(page_sleep), MIN_PAGE_SLEEP)
    items: List[Dict[str, Any]] = []
    seen = set()
    per_keyword_totals: Dict[str, int] = {}
    requests = 0
    truncated = False
    stopped_early = False

    for kw in keywords:
        if stopped_early:
            break
        start = 1
        kw_done = False
        while not kw_done:
            if requests > 0:
                sleep(sleep_sec)
            params = {
                "query": kw,
                "speaker": speaker,
                "nameOfMeeting": nameOfMeeting,
                "from": from_date,
                "until": until_date,
                "limit": page_size,
                "startRecord": start,
            }
            url = _build_url("speech", params)
            data = fetch(url)
            requests += 1
            per_keyword_totals[kw] = int(data.get("numberOfRecords") or 0)
            records = data.get("speechRecord") or []
            if not records:
                kw_done = True
                break
            for rec in records:
                item = _record_to_item(rec)
                sid = item.get("speechID")
                if sid not in seen:
                    seen.add(sid)
                    items.append(item)
                if cap is not None and len(items) >= cap:
                    truncated = True
                    stopped_early = True
                    break
            if progress is not None:
                progress(
                    f"{kw} page {requests}: {len(items)}/{per_keyword_totals[kw]}"
                )
            if stopped_early:
                break
            next_pos = data.get("nextRecordPosition")
            if not next_pos:
                kw_done = True
                break
            start = int(next_pos)

    # 全ページを取り切ったときだけ、ユニーク件数を確定値にする。
    # 途中打ち切りのときはユニーク総数が分からないので total は取得件数のまま。
    # キーワード別合計は重複を含む上限であり、ユニーク総数の代わりにはしない。
    unique_total = len(items)
    upper = sum(per_keyword_totals.values())
    return {
        "total": unique_total,
        "fetched": unique_total,
        "items": items,
        "requests": requests,
        "truncated": truncated,
        "per_keyword_totals": per_keyword_totals,
        "total_upper_bound": upper,
        "total_is_exact": not truncated,
    }


def get_meeting(
    issueID: str,
    fetch: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    会議録全体を取得 (get_meeting 相当)
    返り値: { issueID, date, nameOfMeeting, speeches: list[SpeechItem] }
    """
    if not issueID:
        raise ValueError("issueID を指定してください")

    do_fetch = fetch or _fetch_json
    url = f"{KOKKAI_API_BASE}/meeting?issueID={urllib.parse.quote(issueID)}&recordPacking=json"
    data = do_fetch(url)

    records = data.get("meetingRecord", [])
    if not records:
        raise RuntimeError(f"会議録が見つかりません: {issueID}")

    rec = records[0]
    speeches = [_record_to_item(sp) for sp in (rec.get("speechRecord") or [])]

    return {
        "issueID": rec.get("issueID"),
        "date": rec.get("date"),
        "nameOfMeeting": rec.get("nameOfMeeting"),
        "speeches": speeches,
    }


if __name__ == "__main__":
    # 簡易テスト
    print("=== 検索テスト (生成AI) ===")
    res = search_speeches(query="生成AI", limit=2)
    print(f"総件数: {res['total']}")
    for i, item in enumerate(res["items"], 1):
        print(f"{i}. {item['date']} {item['speaker']}")
        print(f"   {item['speech'][:80]}...")
        print(f"   issueID={item['issueID']}")
    print("\n=== 会議録取得テスト ===")
    if res["items"]:
        meeting = get_meeting(res["items"][0]["issueID"])
        print(f"会議: {meeting['nameOfMeeting']} ({meeting['date']})")
        print(f"発言数: {len(meeting['speeches'])}")
