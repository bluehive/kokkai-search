#!/usr/bin/env python3
"""
Kokkai API クライアント (stdlib のみ)
kokkai-mcp の search_speeches / get_meeting と同等の機能を提供。
"""
import json
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


KOKKAI_API_BASE = "https://kokkai.ndl.go.jp/api"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RECORDS = 30


def _build_url(endpoint: str, params: Dict[str, Any]) -> str:
    """\u691c\u7d22\u30d1\u30e9\u30e1\u30fc\u30bf\u304b\u3089URL\u3092\u69cb\u7bc9"""
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
    """URL\u304b\u3089JSON\u3092\u53d6\u5f97\uff08\u30a8\u30e9\u30fc\u51e6\u7406\u4ed8\u304d\uff09"""
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
        raise RuntimeError(f"API HTTP\u30a8\u30e9\u30fc {e.code}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"API\u63a5\u7d9a\u30a8\u30e9\u30fc: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON\u30d1\u30fc\u30b9\u30a8\u30e9\u30fc: {e}") from e


def search_speeches(
    query: Optional[str] = None,
    speaker: Optional[str] = None,
    nameOfMeeting: Optional[str] = None,
    from_date: Optional[str] = None,
    until_date: Optional[str] = None,
    limit: int = 10,
    start: int = 1,
) -> Dict[str, Any]:
    """
    \u767a\u8a00\u691c\u7d22 (search_speeches \u76f8\u5f53)
    \u8fd4\u308a\u5024: { total: int, items: list[SpeechItem], nextRecordPosition?: int }
    """
    if not any([query, speaker, nameOfMeeting]):
        raise ValueError("query, speaker, nameOfMeeting \u306e\u3044\u305a\u308c\u304b\u3092\u6307\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044")

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
    data = _fetch_json(url)

    items = []
    for rec in data.get("speechRecord", []):
        items.append({
            "speechID": rec.get("speechID"),
            "issueID": rec.get("issueID"),
            "date": rec.get("date"),
            "nameOfMeeting": rec.get("nameOfMeeting"),
            "speaker": rec.get("speaker", ""),
            "speech": rec.get("speech", ""),
            "speechOrder": rec.get("speechOrder"),
            "speechURL": rec.get("speechURL"),
            "meetingURL": rec.get("meetingURL"),
        })

    result = {
        "total": data.get("numberOfRecords", 0),
        "items": items,
    }
    if data.get("nextRecordPosition"):
        result["nextRecordPosition"] = data["nextRecordPosition"]
    return result


def get_meeting(issueID: str) -> Dict[str, Any]:
    """
    \u4f1a\u8b70\u9332\u5168\u4f53\u3092\u53d6\u5f97 (get_meeting \u76f8\u5f53)
    \u8fd4\u308a\u5024: { issueID, date, nameOfMeeting, speeches: list[SpeechItem] }
    """
    if not issueID:
        raise ValueError("issueID \u3092\u6307\u5b9a\u3057\u3066\u304f\u3060\u3055\u3044")

    url = f"{KOKKAI_API_BASE}/meeting?issueID={urllib.parse.quote(issueID)}&recordPacking=json"
    data = _fetch_json(url)

    records = data.get("meetingRecord", [])
    if not records:
        raise RuntimeError(f"\u4f1a\u8b70\u9332\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093: {issueID}")

    rec = records[0]
    speeches = []
    for sp in rec.get("speechRecord", []):
        speeches.append({
            "speechID": sp.get("speechID"),
            "issueID": sp.get("issueID"),
            "date": sp.get("date"),
            "nameOfMeeting": sp.get("nameOfMeeting"),
            "speaker": sp.get("speaker", ""),
            "speech": sp.get("speech", ""),
            "speechOrder": sp.get("speechOrder"),
            "speechURL": sp.get("speechURL"),
            "meetingURL": sp.get("meetingURL"),
        })

    return {
        "issueID": rec.get("issueID"),
        "date": rec.get("date"),
        "nameOfMeeting": rec.get("nameOfMeeting"),
        "speeches": speeches,
    }


if __name__ == "__main__":
    # \u7c21\u6613\u30c6\u30b9\u30c8
    print("=== \u691c\u7d22\u30c6\u30b9\u30c8 (\u751f\u6210AI) ===")
    res = search_speeches(query="\u751f\u6210AI", limit=2)
    print(f"\u7dcf\u4ef6\u6570: {res['total']}")
    for i, item in enumerate(res["items"], 1):
        print(f"{i}. {item['date']} {item['speaker']}")
        print(f"   {item['speech'][:80]}...")
        print(f"   issueID={item['issueID']}")
    print("\n=== \u4f1a\u8b70\u9332\u53d6\u5f97\u30c6\u30b9\u30c8 ===")
    if res["items"]:
        meeting = get_meeting(res["items"][0]["issueID"])
        print(f"\u4f1a\u8b70: {meeting['nameOfMeeting']} ({meeting['date']})")
        print(f"\u767a\u8a00\u6570: {len(meeting['speeches'])}")
