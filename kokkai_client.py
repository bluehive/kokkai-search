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


def search_speeches(
    query: Optional[str] = None,
    speaker: Optional[str] = None,
    nameOfMeeting: Optional[str] = None,
    from_date: Optional[str] = None,
    until_date: Optional[str] = None,
    limit: int = 10,
    start: int = 1,
    or_search: bool = False,
) -> Dict[str, Any]:
    """
    発言検索 (search_speeches 相当)
    or_search=True の場合、query のキーワードのいずれかを含む (OR検索)
    返り値: { total: int, items: list[SpeechItem], nextRecordPosition?: int }
    """
    if not any([query, speaker, nameOfMeeting]):
        raise ValueError("query, speaker, nameOfMeeting のいずれかを指定してください")

    if query and or_search:
        keywords = [k.strip() for k in query.split() if k.strip()]
        if not keywords:
            keywords = [query]
        items = []
        seen = set()
        sub_limit = min(max(limit // max(len(keywords), 1) + 5, 5), 50)
        for kw in keywords:
            sub_params = {
                "query": kw,
                "speaker": speaker,
                "nameOfMeeting": nameOfMeeting,
                "from": from_date,
                "until": until_date,
                "limit": sub_limit,
                "startRecord": start,
            }
            url = _build_url("speech", sub_params)
            data = _fetch_json(url)
            for rec in data.get("speechRecord", []):
                sid = rec.get("speechID")
                if sid not in seen:
                    seen.add(sid)
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
        items = items[:limit]
        total = len(items)  # approximate for OR
        result = {"total": total, "items": items}
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
    会議録全体を取得 (get_meeting 相当)
    返り値: { issueID, date, nameOfMeeting, speeches: list[SpeechItem] }
    """
    if not issueID:
        raise ValueError("issueID を指定してください")

    url = f"{KOKKAI_API_BASE}/meeting?issueID={urllib.parse.quote(issueID)}&recordPacking=json"
    data = _fetch_json(url)

    records = data.get("meetingRecord", [])
    if not records:
        raise RuntimeError(f"会議録が見つかりません: {issueID}")

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
