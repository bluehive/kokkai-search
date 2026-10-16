#!/usr/bin/env python3
"""ページング / JSONL / MD のオフラインテスト。ネットワークは使わない。"""
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cli  # noqa: E402
import kokkai_client  # noqa: E402
import kokkai_report  # noqa: E402


def make_record(sid, **extra):
    rec = {
        "speechID": sid,
        "issueID": f"issue-{sid}",
        "date": "1960-05-20",
        "nameOfHouse": "衆議院",
        "nameOfMeeting": "本会議",
        "issue": "第1号",
        "speaker": "岸信介",
        "speakerGroup": "自由民主党",
        "speakerPosition": "内閣総理大臣",
        "speakerRole": "政府",
        "speechOrder": 1,
        "speech": f"発言本文 {sid}",
        "speechURL": f"https://example.invalid/speech/{sid}",
        "meetingURL": f"https://example.invalid/meeting/{sid}",
    }
    rec.update(extra)
    return rec


class FakeAPI:
    """startRecord / maximumRecords / any を見てメモリ上のページを返す。"""

    def __init__(self, by_keyword):
        # by_keyword: {keyword_or_"": [records...]}
        self.by_keyword = by_keyword
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        start = int(qs.get("startRecord", ["1"])[0])
        size = int(qs.get("maximumRecords", ["30"])[0])
        keyword = qs.get("any", [""])[0]
        records = self.by_keyword.get(keyword, [])
        total = len(records)
        page = records[start - 1: start - 1 + size]
        body = {
            "numberOfRecords": total,
            "speechRecord": page,
        }
        next_pos = start + len(page)
        if page and next_pos <= total:
            body["nextRecordPosition"] = next_pos
        return body


class RecordingSleep:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


class PagingTests(unittest.TestCase):
    def test_paging_collects_all_pages(self):
        records = [make_record(f"s{i:03d}") for i in range(243)]
        api = FakeAPI({"": records})  # query なしは使わない。キーワードで引く。
        api.by_keyword["安保"] = records
        slept = RecordingSleep()
        result = kokkai_client.search_speeches_all(
            query="安保",
            speaker="岸信介",
            page_size=100,
            page_sleep=3.0,
            fetch=api.fetch,
            sleep=slept,
        )
        self.assertEqual(result["requests"], 3)
        self.assertEqual(result["fetched"], 243)
        self.assertEqual(len(result["items"]), 243)
        self.assertEqual(result["total"], 243)
        self.assertFalse(result["truncated"])
        self.assertTrue(result["total_is_exact"])
        self.assertEqual(result["total_upper_bound"], 243)
        self.assertEqual([item["speechID"] for item in result["items"][:2]], ["s000", "s001"])
        self.assertEqual(result["items"][-1]["speechID"], "s242")
        # 最後のページは startRecord=201。nextRecordPosition が無いので 3 リクエストで止まる。
        last = api.urls[-1]
        self.assertIn("startRecord=201", last)
        self.assertIn("maximumRecords=100", last)

    def test_max_total_caps_and_marks_truncated(self):
        records = [make_record(f"s{i:03d}") for i in range(243)]
        api = FakeAPI({"安保": records})
        slept = RecordingSleep()
        result = kokkai_client.search_speeches_all(
            query="安保",
            max_total=150,
            page_size=100,
            fetch=api.fetch,
            sleep=slept,
        )
        self.assertEqual(result["requests"], 2)
        self.assertEqual(result["fetched"], 150)
        self.assertEqual(len(result["items"]), 150)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total"], 243)
        # 非 OR は API の numberOfRecords が分かるので、打ち切っても exact。
        self.assertTrue(result["total_is_exact"])
        self.assertEqual(result["total_upper_bound"], 243)

    def test_sleep_between_requests_only_and_floor_is_3(self):
        records = [make_record(f"s{i:03d}") for i in range(243)]
        api = FakeAPI({"安保": records})
        slept = RecordingSleep()
        kokkai_client.search_speeches_all(
            query="安保",
            page_sleep=0.5,
            fetch=api.fetch,
            sleep=slept,
        )
        self.assertEqual(len(slept.calls), 2)  # 3 requests → 2 sleeps
        self.assertTrue(all(sec >= 3.0 for sec in slept.calls))

    def test_or_dedupes_and_sleeps_across_keywords(self):
        kw_a = [make_record("shared"), make_record("only-a")]
        kw_b = [make_record("shared"), make_record("only-b"), make_record("only-b2")]
        api = FakeAPI({"共産主義": kw_a, "共産党": kw_b})
        slept = RecordingSleep()
        result = kokkai_client.search_speeches_all(
            query="共産主義 共産党",
            or_search=True,
            page_size=100,
            page_sleep=3.0,
            fetch=api.fetch,
            sleep=slept,
        )
        ids = [item["speechID"] for item in result["items"]]
        self.assertEqual(ids, ["shared", "only-a", "only-b", "only-b2"])
        self.assertEqual(result["fetched"], 4)
        self.assertEqual(result["total"], 4)
        self.assertFalse(result["truncated"])
        self.assertTrue(result["total_is_exact"])
        # 上限は重複を含むキーワード別合計。ユニーク件数より大きくてよい。
        self.assertEqual(result["total_upper_bound"], 5)
        self.assertEqual(result["per_keyword_totals"], {"共産主義": 2, "共産党": 3})
        self.assertEqual(result["requests"], 2)
        # キーワードをまたぐ間隔も含め、リクエストのあいだだけ 1 回待つ。
        self.assertEqual(len(slept.calls), 1)
        self.assertGreaterEqual(slept.calls[0], 3.0)

    def test_or_max_total_stops_on_unique_count(self):
        kw_a = [make_record(f"a{i}") for i in range(3)]
        kw_b = [make_record(f"b{i}") for i in range(5)]
        api = FakeAPI({"甲": kw_a, "乙": kw_b})
        slept = RecordingSleep()
        result = kokkai_client.search_speeches_all(
            query="甲 乙",
            or_search=True,
            max_total=4,
            fetch=api.fetch,
            sleep=slept,
        )
        self.assertEqual(result["fetched"], 4)
        self.assertTrue(result["truncated"])
        # 打ち切り時のユニーク総数は不明。total は取得件数のまま。
        self.assertEqual(result["total"], 4)
        self.assertFalse(result["total_is_exact"])
        self.assertEqual(result["total_upper_bound"], 8)
        self.assertEqual(result["per_keyword_totals"], {"甲": 3, "乙": 5})
        # 1キーワード目で 3 件、2キーワード目の先頭ページで上限に達するので 2 リクエスト。
        self.assertEqual(result["requests"], 2)
        self.assertEqual(len(slept.calls), 1)

    def test_search_speeches_or_uses_record_to_item_and_dedupes(self):
        kw_a = [make_record("shared", speakerPosition="総理")]
        kw_b = [make_record("shared"), make_record("other")]
        api = FakeAPI({"甲": kw_a, "乙": kw_b})
        result = kokkai_client.search_speeches(
            query="甲 乙",
            or_search=True,
            limit=10,
            fetch=api.fetch,
        )
        ids = [item["speechID"] for item in result["items"]]
        self.assertEqual(ids, ["shared", "other"])
        self.assertEqual(result["items"][0]["speakerPosition"], "総理")
        self.assertEqual(result["items"][0]["nameOfHouse"], "衆議院")
        self.assertEqual(result["per_keyword_totals"], {"甲": 1, "乙": 2})
        self.assertEqual(result["total"], 2)

    def test_build_url_caps_maximum_records_and_passes_start(self):
        url = kokkai_client._build_url("speech", {"query": "安保", "limit": 500, "startRecord": 201})
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(qs["maximumRecords"], ["100"])
        self.assertEqual(qs["startRecord"], ["201"])


class OutputTests(unittest.TestCase):
    def _items(self, n=2):
        return [kokkai_client._record_to_item(make_record(f"s{i}")) for i in range(n)]

    def test_jsonl_and_meta(self):
        items = self._items(2)
        params = {
            "query": "安保 改定",
            "or": False,
            "speaker": "岸信介",
            "nameOfMeeting": None,
            "from": "1960-01-01",
            "until": "1960-07-31",
        }
        result = {
            "total": 10,
            "fetched": 2,
            "items": items,
            "truncated": True,
            "requests": 1,
            "per_keyword_totals": None,
            "total_is_exact": True,
            "total_upper_bound": 10,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = cli.write_jsonl(os.path.join(tmp, "out.jsonl"), items, params)
            meta = cli.write_meta(path, {**params, "fetch_all": True, "max_total": 50, "limit": 10}, result, 3.0)
            lines = Path(path).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            row = json.loads(lines[0])
            for key in (
                "speechID", "issueID", "date", "nameOfHouse", "nameOfMeeting",
                "speaker", "speakerGroup", "speakerPosition", "speech",
                "speechURL", "meetingURL", "query", "or", "speaker_filter",
                "from", "until",
            ):
                self.assertIn(key, row)
            self.assertEqual(row["speaker_filter"], "岸信介")
            self.assertFalse(row["or"])
            self.assertIn("発言本文", row["speech"])  # ensure_ascii=False
            meta_obj = json.loads(Path(meta).read_text(encoding="utf-8"))
            self.assertEqual(meta_obj["total_hits"], 10)
            self.assertEqual(meta_obj["total_hits_upper_bound"], 10)
            self.assertTrue(meta_obj["total_is_exact"])
            self.assertEqual(meta_obj["fetched"], 2)
            self.assertTrue(meta_obj["truncated"])
            self.assertEqual(meta_obj["api_base"], kokkai_client.KOKKAI_API_BASE)
            self.assertTrue(meta.endswith(".meta.json"))

    def test_jsonl_directory_autofilename(self):
        items = self._items(1)
        params = {"query": "三島", "speaker": "佐藤", "from": "1970-11-25"}
        with tempfile.TemporaryDirectory() as tmp:
            target = tmp + os.sep
            path = cli.write_jsonl(target, items, params)
            self.assertTrue(path.endswith(".jsonl"))
            self.assertIn("三島", os.path.basename(path))
            self.assertIn("佐藤", os.path.basename(path))
            self.assertTrue(os.path.isfile(path))

    def test_md_header_fetched_and_truncation(self):
        items = self._items(2)
        params = {"query": "安保", "speaker": "岸信介", "fetched": 2, "truncated": True, "fetch_all": True}
        text = kokkai_report.generate_markdown(items, params, total=243)
        self.assertIn("- 総ヒット数: 243", text)
        self.assertIn("- 取得件数: 2", text)
        self.assertIn("切り詰め", text)
        self.assertIn("全件 (--all)", text)

    def test_md_not_truncated_has_no_warning(self):
        items = self._items(2)
        params = {"query": "安保", "fetched": 2, "limit": 10}
        text = kokkai_report.generate_markdown(items, params, total=2)
        self.assertIn("- 取得件数: 2", text)
        self.assertNotIn("切り詰め", text)

    def test_md_or_truncated_hides_unknown_unique_total(self):
        items = self._items(2)
        params = {
            "query": "平和安全法制 集団的自衛権",
            "or": True,
            "fetched": 150,
            "truncated": True,
            "fetch_all": True,
            "max_total": 150,
            "total_is_exact": False,
            "total_upper_bound": 370,
        }
        text = kokkai_report.generate_markdown(items, params, total=150)
        self.assertIn("- 総ヒット数: 不明（キーワード別合計の上限 370）", text)
        self.assertNotIn("- 総ヒット数: 150", text)
        self.assertIn("- 取得件数: 150", text)
        self.assertIn("取得上限 150 件に達したため全件を網羅していません", text)
        self.assertNotIn("総ヒット数より少ない", text)

    def test_md_or_exact_shows_unique_total(self):
        items = self._items(2)
        params = {
            "query": "三島 市ヶ谷",
            "or": True,
            "fetched": 6,
            "truncated": False,
            "total_is_exact": True,
            "total_upper_bound": 8,
        }
        text = kokkai_report.generate_markdown(items, params, total=6)
        self.assertIn("- 総ヒット数: 6", text)
        self.assertNotIn("不明", text)
        self.assertNotIn("切り詰め", text)


class CliTests(unittest.TestCase):
    def test_cli_all_jsonl_outdir(self):
        records = [make_record(f"s{i:03d}") for i in range(5)]
        api = FakeAPI({"安保": records})
        slept = RecordingSleep()
        orig_all = cli.search_speeches_all

        def patched_all(*args, **kwargs):
            kwargs["fetch"] = api.fetch
            kwargs["sleep"] = slept
            return kokkai_client.search_speeches_all(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            argv = [
                "--query", "安保",
                "--speaker", "岸信介",
                "--from", "1960-01-01",
                "--until", "1960-07-31",
                "--all",
                "--jsonl", tmp + "/",
                "--outdir", tmp,
                "--json",
            ]
            cli.search_speeches_all = patched_all
            try:
                cli.main(argv)
            finally:
                cli.search_speeches_all = orig_all

            jsonl_files = list(Path(tmp).glob("*.jsonl"))
            meta_files = list(Path(tmp).glob("*.meta.json"))
            md_files = list(Path(tmp).glob("*.md"))
            self.assertEqual(len(jsonl_files), 1)
            self.assertEqual(len(meta_files), 1)
            self.assertEqual(len(md_files), 1)
            rows = [json.loads(line) for line in jsonl_files[0].read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[0]["query"], "安保")
            meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
            self.assertEqual(meta["total_hits"], 5)
            self.assertTrue(meta["total_is_exact"])
            self.assertEqual(meta["total_hits_upper_bound"], 5)
            self.assertEqual(meta["fetched"], 5)
            self.assertFalse(meta["truncated"])
            md = md_files[0].read_text(encoding="utf-8")
            self.assertIn("- 取得件数: 5", md)
            self.assertIn("全件 (--all)", md)
            # 1ページだけなので sleep は呼ばれない。
            self.assertEqual(slept.calls, [])

    def test_cli_page_sleep_floor_warning(self):
        records = [make_record("s0"), make_record("s1")]
        # 2ページにして sleep が 1 回入るようにする。
        api = FakeAPI({"安保": records})
        slept = RecordingSleep()
        orig_all = cli.search_speeches_all

        def patched_all(*args, **kwargs):
            kwargs["fetch"] = api.fetch
            kwargs["sleep"] = slept
            kwargs["page_size"] = 1
            return kokkai_client.search_speeches_all(*args, **kwargs)

        import io
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            argv = [
                "--query", "安保",
                "--all",
                "--page-sleep", "0.5",
                "--max-total", "2",
                "--outdir", tmp,
                "--json",
            ]
            cli.search_speeches_all = patched_all
            old = sys.stderr
            sys.stderr = buf
            try:
                cli.main(argv)
            finally:
                sys.stderr = old
                cli.search_speeches_all = orig_all
        self.assertIn("引き上げ", buf.getvalue())
        self.assertTrue(all(sec >= 3.0 for sec in slept.calls))
        self.assertGreaterEqual(len(slept.calls), 1)


class BatchHelperTests(unittest.TestCase):
    def test_sleep_floor_and_outdir_placeholder(self):
        import kokkai_batch
        self.assertEqual(kokkai_batch.enforce_sleep_bounds(1, 2)[0], 3.0)
        self.assertEqual(kokkai_batch.substitute_outdir("--jsonl {outdir}/", "/tmp/out"), "--jsonl /tmp/out/")

    def test_japanism_queries_unique_filenames(self):
        import shlex
        text = (ROOT / "japanism_queries.txt").read_text(encoding="utf-8")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        self.assertEqual(len(lines), 6)
        names = []
        for line in lines:
            self.assertIn("--all", line)
            self.assertIn("--jsonl {outdir}/", line)
            self.assertIn("--outdir {outdir}", line)
            argv = shlex.split(line)
            params = {"query": "", "speaker": "", "from": ""}
            i = 0
            while i < len(argv):
                flag = argv[i]
                if flag in ("--query", "--or-query", "--speaker", "--from") and i + 1 < len(argv):
                    key = "query" if flag in ("--query", "--or-query") else flag.lstrip("-")
                    params[key] = argv[i + 1]
                    i += 2
                    continue
                i += 1
            # 出力名は日付-クエリ-発言者-from。日付は今日で共通なので、残りで一意なら衝突しない。
            base = kokkai_report.build_output_basename(params, ".jsonl")
            names.append(base.split("-", 1)[1])
        self.assertEqual(len(names), len(set(names)), names)
        self.assertTrue(any("佐藤栄作" in ln for ln in lines))
        self.assertTrue(any("安倍晋三" in ln for ln in lines))
        self.assertFalse(any("安保 改定" in ln or '安保 改定' in ln for ln in lines))


if __name__ == "__main__":
    unittest.main()
