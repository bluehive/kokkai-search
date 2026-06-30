#!/usr/bin/env python3
"""
Kokkai 検索システム Webサーバー (stdlib のみ)
使い方:
  python server.py
  ブラウザで http://localhost:8765 を開く

kokkai-mcp の search_speeches / get_meeting をブラウザで簡単に使えるようにしたものです。
"""
import json
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import URLError, HTTPError

KOKKAI_API = "https://kokkai.ndl.go.jp/api"
PORT = 8765


def proxy_kokkai(endpoint: str, params: dict) -> dict:
    """Kokkai API にプロキシして JSON を返す"""
    q = {}
    for k, v in params.items():
        if v:
            q[k] = v
    q["recordPacking"] = "json"

    # ページングパラメータは /meeting の issueID 指定取得では追加しない（APIが400エラーを返す）
    if endpoint != "meeting" or "issueID" not in q:
        if "maximumRecords" not in q and "limit" not in q:
            q["maximumRecords"] = "20"
        if "startRecord" not in q:
            q["startRecord"] = "1"

    # any / speaker 等にマッピング
    if "query" in q:
        q["any"] = q.pop("query")
    if "limit" in q:
        q["maximumRecords"] = q.pop("limit")

    url = f"{KOKKAI_API}/{endpoint}?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "kokkai-search-web/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def format_speech_record(rec: dict) -> dict:
    """APIレスポンスを統一した形に"""
    return {
        "speechID": rec.get("speechID"),
        "issueID": rec.get("issueID"),
        "date": rec.get("date"),
        "nameOfMeeting": rec.get("nameOfMeeting"),
        "speaker": rec.get("speaker"),
        "speech": rec.get("speech", ""),
        "speechOrder": rec.get("speechOrder"),
        "speechURL": rec.get("speechURL"),
        "meetingURL": rec.get("meetingURL"),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 簡単なクエリ正規化 (最初の値だけ)
        params = {k: v[0] for k, v in qs.items()}

        try:
            if path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(self._html().encode("utf-8"))
                return

            if path == "/search":
                # search_speeches 互換
                api_params = {
                    "any": params.get("query"),
                    "speaker": params.get("speaker"),
                    "nameOfMeeting": params.get("nameOfMeeting"),
                    "from": params.get("from"),
                    "until": params.get("until"),
                    "maximumRecords": params.get("limit", "20"),
                    "startRecord": params.get("start", "1"),
                }
                data = proxy_kokkai("speech", api_params)
                items = [format_speech_record(r) for r in data.get("speechRecord", [])]
                result = {
                    "total": data.get("numberOfRecords", 0),
                    "items": items,
                    "startRecord": data.get("startRecord", 1),
                    "nextRecordPosition": data.get("nextRecordPosition"),
                }
                self._json(result)
                return

            if path == "/meeting":
                issue_id = params.get("issueID")
                if not issue_id:
                    self._error(400, "issueID が必要です")
                    return
                data = proxy_kokkai("meeting", {"issueID": issue_id})
                recs = data.get("meetingRecord", [])
                if not recs:
                    self._error(404, "会議録が見つかりません")
                    return
                m = recs[0]
                speeches = [format_speech_record(s) for s in m.get("speechRecord", [])]
                result = {
                    "issueID": m.get("issueID"),
                    "date": m.get("date"),
                    "nameOfMeeting": m.get("nameOfMeeting"),
                    "speeches": speeches,
                }
                self._json(result)
                return

            self._error(404, "Not found")
        except (HTTPError, URLError) as e:
            msg = str(e)
            self._error(502, f"Kokkai API エラー: {msg}")
        except Exception as e:
            self._error(500, f"サーバーエラー: {e}")

    def _json(self, obj: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _error(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        print(f"[server] {args[0]}")

    def _html(self) -> str:
        # Tailwind CDN + きれいなUI。すべて1ファイル。
        return """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>国会議事録検索システム</title>
  <style>
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e2937; margin:0; }
    .max-w-5xl { max-width: 64rem; margin-left:auto; margin-right:auto; }
    .mx-auto { margin-left:auto; margin-right:auto; }
    .p-6 { padding: 1.5rem; }
    .bg-white { background: #fff; }
    .bg-slate-50 { background: #f8fafc; }
    .bg-slate-100 { background: #f1f5f9; }
    .text-slate-800 { color: #1e2937; }
    .text-slate-700 { color: #334155; }
    .text-slate-600 { color: #475569; }
    .text-slate-500 { color: #64748b; }
    .text-slate-400 { color: #94a3b8; }
    .text-blue-600 { color: #2563eb; }
    .text-blue-500 { color: #3b82f6; }
    .text-emerald-600 { color: #059669; }
    .text-red-700 { color: #b91c1c; }
    .border { border: 1px solid #e2e8f0; }
    .rounded-2xl { border-radius: 1rem; }
    .rounded-xl { border-radius: .75rem; }
    .rounded-full { border-radius: 9999px; }
    .shadow { box-shadow: 0 1px 3px rgb(0 0 0 / 0.1); }
    .p-4 { padding: 1rem; }
    .p-6 { padding: 1.5rem; }
    .px-6 { padding-left:1.5rem; padding-right:1.5rem; }
    .py-2\\.5 { padding-top:.625rem; padding-bottom:.625rem; }
    .py-1\\.5 { padding-top:.375rem; padding-bottom:.375rem; }
    .py-1 { padding-top:.25rem; padding-bottom:.25rem; }
    .mt-1 { margin-top:.25rem; }
    .mt-1\\.5 { margin-top:.375rem; }
    .mt-3 { margin-top:.75rem; }
    .mt-4 { margin-top:1rem; }
    .mt-10 { margin-top:2.5rem; }
    .mb-3 { margin-bottom:.75rem; }
    .mb-6 { margin-bottom:1.5rem; }
    .ml-2 { margin-left:.5rem; }
    .ml-auto { margin-left:auto; }
    .flex { display:flex; }
    .grid { display:grid; }
    .gap-2 { gap:.5rem; }
    .gap-3 { gap:.75rem; }
    .gap-4 { gap:1rem; }
    .items-center { align-items:center; }
    .items-start { align-items:flex-start; }
    .justify-between { justify-content:space-between; }
    .text-3xl { font-size:1.875rem; line-height:2.25rem; }
    .text-xl { font-size:1.25rem; line-height:1.75rem; }
    .text-lg { font-size:1.125rem; line-height:1.75rem; }
    .text-sm { font-size:.875rem; line-height:1.25rem; }
    .text-xs { font-size:.75rem; line-height:1rem; }
    .font-bold { font-weight:700; }
    .font-semibold { font-weight:600; }
    .font-medium { font-weight:500; }
    .font-mono { font-family: ui-monospace, monospace; }
    .whitespace-nowrap { white-space:nowrap; }
    .min-w-0 { min-width:0; }
    .flex-1 { flex:1; }
    .hidden { display:none; }
    .cursor-pointer { cursor:pointer; }
    .transition { transition: all .1s; }
    .space-y-3 > * + * { margin-top: .75rem; }
    .disabled\\:opacity-40:disabled { opacity: .4; }
    .result-card { transition: box-shadow .1s; border:1px solid #e2e8f0; border-radius:1rem; padding:1rem; background:#fff; }
    .result-card:hover { box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1); }
    .speech { white-space: pre-wrap; line-height: 1.65; }
    .max-w-4xl { max-width: 56rem; }
    .fixed { position:fixed; }
    .inset-0 { top:0; right:0; bottom:0; left:0; }
    .z-50 { z-index:50; }
    .overflow-auto { overflow:auto; }
    .overflow-hidden { overflow:hidden; }
    .bg-black\\/50 { background: rgba(0,0,0,.5); }
    .border-l-4 { border-left: 4px solid #bfdbfe; }
    .pl-4 { padding-left:1rem; }
    .px-3 { padding-left:.75rem; padding-right:.75rem; }
    .px-5 { padding-left:1.25rem; padding-right:1.25rem; }
    .py-3 { padding-top:.75rem; padding-bottom:.75rem; }
    .py-4 { padding-top:1rem; padding-bottom:1rem; }
    .border-b { border-bottom:1px solid #e2e8f0; }
    .border-t { border-top:1px solid #e2e8f0; }
    .text-center { text-align:center; }
    .self-center { align-self:center; }
    .hover\\:bg-blue-700:hover { background:#1d4ed8; }
    .hover\\:bg-white:hover { background:#fff; }
    .hover\\:underline:hover { text-decoration:underline; }
    .hover\\:bg-slate-100:hover { background:#f1f5f9; }
    .active\\:bg-blue-800:active { background:#1e40af; }
    .focus\\:outline-none:focus { outline:none; }
    .focus\\:ring-2:focus { box-shadow: 0 0 0 2px #3b82f6; }
    .bg-blue-600 { background:#2563eb; color:#fff; }
    .bg-red-50 { background:#fef2f2; }
    .w-full { width:100%; }
    .block { display:block; }
  </style>
</head>
<body class="bg-slate-50">
  <div class="max-w-5xl mx-auto p-6">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-3xl font-bold text-slate-800">📜 国会議事録検索</h1>
        <p class="text-slate-600 mt-1">kokkai-mcp と同じ国立国会図書館APIを使用した検索システム</p>
      </div>
      <div class="text-sm text-slate-500">
        <a href="https://github.com/harutomo51/kokkai-mcp" target="_blank" class="underline">kokkai-mcp</a> 利用例
      </div>
    </div>

    <!-- 検索フォーム -->
    <div class="bg-white rounded-2xl shadow p-6 mb-6">
      <div class="grid grid-cols-3 gap-4" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));">
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">キーワード (本文 AND)</label>
          <input id="query" type="text" placeholder="生成AI 規制" class="w-full border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
        </div>
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">発言者</label>
          <input id="speaker" type="text" placeholder="岸田" class="w-full border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
        </div>
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">会議名</label>
          <input id="nameOfMeeting" type="text" placeholder="予算委員会" class="w-full border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
        </div>
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">開始日</label>
          <input id="from" type="date" class="w-full border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
        </div>
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">終了日</label>
          <input id="until" type="date" class="w-full border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
        </div>
        <div>
          <label class="block text-sm font-medium text-slate-700 mb-1">最大件数</label>
          <select id="limit" class="w-full border rounded-xl px-3 py-2 text-sm">
            <option value="10">10</option>
            <option value="20" selected>20</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </div>
      </div>

      <div class="mt-4 flex gap-3">
        <button id="search-btn"
                class="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-medium rounded-2xl transition flex items-center gap-2">
          🔍 検索
        </button>
        <button id="reset-btn" 
                class="px-5 py-2.5 border border-slate-300 hover:bg-slate-100 rounded-2xl text-sm transition">リセット</button>
        <div class="flex-1"></div>
        <div class="text-xs text-slate-500 self-center">公式API直接利用（要約は別途MCP推奨）</div>
      </div>
    </div>

    <!-- 結果 -->
    <div id="results-section" class="hidden">
      <div class="flex items-center justify-between mb-3 px-1">
        <div>
          <span id="result-count" class="font-semibold text-lg"></span>
          <span class="text-slate-500 text-sm ml-2" id="result-range"></span>
        </div>
        <div class="flex gap-2">
          <button id="prev-btn" onclick="prevPage()" 
                  class="px-3 py-1.5 text-sm border rounded-xl hover:bg-white disabled:opacity-40">← 前へ</button>
          <button id="next-btn" onclick="nextPage()" 
                  class="px-3 py-1.5 text-sm border rounded-xl hover:bg-white disabled:opacity-40">次へ →</button>
        </div>
      </div>

      <div id="results" class="space-y-3"></div>

      <div id="pdf-action" class="mt-6 pt-4 border-t hidden">
        <button onclick="exportToPDF()"
                class="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-2xl transition flex items-center gap-2">
          📄 出力された一覧をPDF文書にまとめる
        </button>
        <p class="text-xs text-slate-500 mt-2">検索条件と各発言の全文・URLを記載したPDF形式の報告書を生成します。</p>
      </div>
    </div>

    <div id="loading" class="hidden text-center py-10 text-slate-500">読み込み中...</div>
    <div id="error" class="hidden mt-4 p-4 bg-red-50 text-red-700 rounded-2xl"></div>

    <!-- 全体会議録モーダル -->
    <div id="modal" onclick="if (event.target.id === 'modal') hideModal()" class="hidden fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div onclick="event.stopImmediatePropagation()" class="bg-white w-full max-w-4xl max-h-[90vh] rounded-3xl shadow-xl overflow-hidden flex flex-col">
        <div class="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <div id="modal-title" class="font-semibold text-xl"></div>
            <div id="modal-meta" class="text-sm text-slate-500"></div>
          </div>
          <button onclick="hideModal()" class="text-2xl leading-none px-3 py-1 text-slate-400 hover:text-slate-700">×</button>
        </div>
        <div id="modal-body" class="overflow-auto p-6 text-sm space-y-4 flex-1"></div>
        <div class="px-6 py-3 border-t text-xs text-slate-500 flex justify-between">
          <div>issueID: <span id="modal-issue"></span></div>
          <a id="modal-link" target="_blank" class="text-blue-600 hover:underline">公式ページを開く</a>
        </div>
      </div>
    </div>

    <div class="mt-10 text-xs text-slate-500 px-1">
      <strong>注意:</strong> このシステムは国立国会図書館の<a href="https://kokkai.ndl.go.jp/api.html" class="underline">国会議事録検索システムAPI</a>を利用しています。
      kokkai-mcp と同等の検索が可能です。要約・比較分析などの高度機能は <code>kokkai-mcp</code> + Claude を使用してください。
    </div>
  </div>

<script>
let currentParams = {};
let currentStart = 1;
let currentResults = [];

function resetForm() {
  ["query","speaker","nameOfMeeting","from","until"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  const limitEl = document.getElementById("limit");
  if (limitEl) limitEl.value = "20";
}

function showError(msg) {
  const err = document.getElementById("error");
  if (err) {
    err.textContent = msg;
    err.classList.remove("hidden");
    err.style.display = "block";
  } else {
    alert(msg);
  }
}

async function doSearch(start = 1) {
  const queryEl = document.getElementById("query");
  const speakerEl = document.getElementById("speaker");
  const meetingEl = document.getElementById("nameOfMeeting");
  const fromEl = document.getElementById("from");
  const untilEl = document.getElementById("until");
  const limitEl = document.getElementById("limit");

  const query = (queryEl ? queryEl.value.trim() : "");
  const speaker = (speakerEl ? speakerEl.value.trim() : "");
  const nameOfMeeting = (meetingEl ? meetingEl.value.trim() : "");
  const from = (fromEl ? fromEl.value : "");
  const until = (untilEl ? untilEl.value : "");
  const limit = (limitEl ? limitEl.value : "20");

  if (!query && !speaker && !nameOfMeeting) {
    alert("キーワード・発言者・会議名のいずれかを入力してください");
    return;
  }

  currentParams = { query, speaker, nameOfMeeting, from, until, limit };
  currentStart = start;

  showLoading(true);
  const errEl = document.getElementById("error");
  if (errEl) {
    errEl.classList.add("hidden");
    errEl.style.display = "none";
  }

  // 新しい検索時は一旦PDFボタンを隠す
  const pdfAction = document.getElementById("pdf-action");
  if (pdfAction) pdfAction.classList.add("hidden");

  try {
    const qs = new URLSearchParams({ ...currentParams, start: String(start) });
    const res = await fetch("/search?" + qs.toString());
    if (!res.ok) {
      const txt = await res.text();
      throw new Error("サーバーエラー: " + res.status + " " + txt.slice(0,100));
    }
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    renderResults(data);
  } catch (e) {
    console.error("Search error:", e);
    showError("検索に失攷しました: " + (e.message || e));
  } finally {
    showLoading(false);
  }
}

function renderResults(data) {
  const container = document.getElementById("results");
  if (!container) return;

  container.innerHTML = "";

  const section = document.getElementById("results-section");
  if (section) {
    section.classList.remove("hidden");
    section.style.display = "block";
  }

  const pdfAction = document.getElementById("pdf-action");
  if (pdfAction) pdfAction.classList.remove("hidden");

  const countEl = document.getElementById("result-count");
  if (countEl) {
    countEl.textContent = (data.total || 0).toLocaleString() + " 件ヒット";
  }

  const rangeEl = document.getElementById("result-range");
  if (rangeEl) {
    const itemLen = (data.items || []).length;
    const end = currentStart + itemLen - 1;
    rangeEl.textContent = itemLen ? `(${currentStart}〜${end}件目)` : "";
  }

  const prev = document.getElementById("prev-btn");
  const next = document.getElementById("next-btn");
  if (prev) prev.disabled = currentStart <= 1;
  if (next) next.disabled = !data.nextRecordPosition;

  const items = data.items || [];
  currentResults = items;

  if (items.length === 0) {
    const noRes = document.createElement("div");
    noRes.className = "p-4 bg-white border rounded-2xl text-slate-500";
    noRes.textContent = "該当する発言が見つかりませんでした。検索条件を変更してみてください。";
    container.appendChild(noRes);

    const pdfAction = document.getElementById("pdf-action");
    if (pdfAction) pdfAction.classList.add("hidden");
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "result-card bg-white border rounded-2xl p-4 cursor-pointer";
    card.onclick = () => loadFullMeeting(item.issueID, item);

    const speechShort = (item.speech || "").slice(0, 220).replace(/\\r?\\n/g, " ");

    // Use textContent for safety where possible, but keep simple template for structure
    card.innerHTML = `
      <div class="flex justify-between items-start gap-4">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 text-sm">
            <span class="font-medium text-slate-800">${item.date || ""}</span>
            <span class="px-2 py-0.5 text-xs rounded-full bg-slate-100 text-slate-600">${item.nameOfMeeting || ""}</span>
          </div>
          <div class="font-semibold text-lg mt-0.5 text-slate-900">${item.speaker || "(発言者不明)"}</div>
          <div class="text-sm text-slate-600 mt-1.5 speech"></div>
        </div>
        <div class="text-right text-xs whitespace-nowrap text-slate-400">
          <div>issueID</div>
          <div class="font-mono text-[10px] text-blue-600">${item.issueID || ""}</div>
        </div>
      </div>
      <div class="mt-3 text-xs flex gap-3">
        ${item.speechURL ? `<a href="${item.speechURL}" target="_blank" onclick="event.stopImmediatePropagation()" class="text-blue-600 hover:underline">発言ページ →</a>` : ""}
        ${item.meetingURL ? `<a href="${item.meetingURL}" target="_blank" onclick="event.stopImmediatePropagation()" class="text-blue-600 hover:underline">会議録ページ →</a>` : ""}
        <span class="text-emerald-600 ml-auto text-[10px] self-center">クリックで全文表示</span>
      </div>
    `;

    // Safely set speech text to avoid breaking HTML with special chars
    const speechDiv = card.querySelector(".speech");
    if (speechDiv) {
      speechDiv.textContent = speechShort + (item.speech && item.speech.length > 220 ? "..." : "");
    }

    container.appendChild(card);
  });

  // PDFボタンを有効化 (already shown above, but ensure visible)
  if (pdfAction) pdfAction.classList.remove("hidden");
}

function escapeHtml(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function exportToPDF() {
  if (!currentResults || currentResults.length === 0) {
    alert("検索結果がありません。先に検索を実行してください。");
    return;
  }

  const p = currentParams || {};
  const now = new Date().toLocaleString("ja-JP");

  // 検索条件のテキスト（PDF冒頭に一度だけ）
  let conditionsHtml = `
    <h2 style="font-size:16pt; border-bottom:1px solid #ccc; padding-bottom:4px;">検索条件</h2>
    <table style="border-collapse: collapse; margin-bottom: 1em; font-size: 11pt;">
      <tr><td style="padding:2px 8px; font-weight:bold; width:120px;">キーワード</td><td>${escapeHtml(p.query || "（指定なし）")}</td></tr>
      <tr><td style="padding:2px 8px; font-weight:bold;">発言者</td><td>${escapeHtml(p.speaker || "（指定なし）")}</td></tr>
      <tr><td style="padding:2px 8px; font-weight:bold;">会議名</td><td>${escapeHtml(p.nameOfMeeting || "（指定なし）")}</td></tr>
      <tr><td style="padding:2px 8px; font-weight:bold;">期間</td><td>${escapeHtml(p.from || "")} 〜 ${escapeHtml(p.until || "")}</td></tr>
      <tr><td style="padding:2px 8px; font-weight:bold;">取得上限</td><td>${escapeHtml(p.limit || "20")} 件</td></tr>
    </table>
    <p style="font-size:10pt; color:#555;">出力日時: ${escapeHtml(now)}　／　ヒット件数: ${currentResults.length} 件（表示分）</p>
  `;

  // 各発言
  let itemsHtml = currentResults.map((item, idx) => {
    const fullUrl = item.speechURL || "";
    const meetingUrl = item.meetingURL || "";
    const speech = escapeHtml(item.speech || "");

    return `
      <div style="page-break-inside: avoid; margin-bottom: 1.2em; border-bottom: 1px solid #eee; padding-bottom: 0.8em;">
        <div style="font-weight: bold; font-size: 12pt; margin-bottom: 4px;">
          【${idx + 1}】 ${escapeHtml(item.date || "日付不明")}　${escapeHtml(item.speaker || "発言者不明")}
        </div>
        <div style="font-size: 10pt; color: #444; margin-bottom: 4px;">
          会議: ${escapeHtml(item.nameOfMeeting || "")}
        </div>
        <div style="white-space: pre-wrap; font-size: 10pt; line-height: 1.5; margin: 6px 0; background: #f9f9f9; padding: 8px; border-left: 3px solid #ccc;">
          ${speech}
        </div>
        <div style="font-size: 9pt;">
          <strong>発言URL:</strong> <a href="${fullUrl}" style="color:#0066cc; word-break: break-all;">${fullUrl || "なし"}</a><br>
          <strong>会議録URL:</strong> <a href="${meetingUrl}" style="color:#0066cc; word-break: break-all;">${meetingUrl || "なし"}</a>
        </div>
      </div>
    `;
  }).join("");

  const reportHtml = `
    <!DOCTYPE html>
    <html lang="ja">
    <head>
      <meta charset="UTF-8">
      <title>国会議事録検索結果</title>
      <style>
        body { font-family: "Yu Gothic", "Hiragino Sans", sans-serif; font-size: 11pt; line-height: 1.6; padding: 30px; max-width: 800px; margin: 0 auto; color: #222; }
        h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 6px; }
        h2 { font-size: 14pt; }
        @media print {
          body { padding: 15mm; font-size: 10pt; }
          .no-print { display: none !important; }
          .page-break { page-break-before: always; }
        }
        a { color: #0066cc; text-decoration: none; }
      </style>
    </head>
    <body>
      <div class="no-print" style="margin-bottom: 20px; padding: 10px; background: #f0f0f0; border-radius: 6px;">
        <button onclick="window.print()" style="padding: 8px 16px; font-size: 12pt; background:#059669; color:white; border:none; border-radius:6px; cursor:pointer;">
          📄 このページをPDFとして保存（印刷ダイアログで「PDFとして保存」を選択）
        </button>
        <p style="margin: 8px 0 0 0; font-size: 9pt; color:#666;">
          ブラウザの印刷機能を使ってPDFファイルに変換してください。検索条件と各発言の完全なURLが記載されています。
        </p>
      </div>

      <h1>国会議事録検索結果</h1>

      ${conditionsHtml}

      <h2 style="font-size:16pt; border-bottom:1px solid #ccc; padding-bottom:4px; margin-top: 1.5em;">議事発言一覧</h2>

      ${itemsHtml}

      <p style="margin-top: 2em; font-size: 9pt; color: #777; border-top: 1px solid #ddd; padding-top: 8px;">
        本資料は国立国会図書館「国会議事録検索システムAPI」を利用して生成しました。<br>
        詳細は <a href="https://kokkai.ndl.go.jp/">https://kokkai.ndl.go.jp/</a> をご確認ください。
      </p>
    </body>
    </html>
  `;

  const win = window.open("", "_blank");
  if (!win) {
    alert("ポップアップブロックを解除して再試行してください。");
    return;
  }
  win.document.write(reportHtml);
  win.document.close();
}

async function loadFullMeeting(issueID, hintItem = null) {
  showLoading(true);
  try {
    const res = await fetch("/meeting?issueID=" + encodeURIComponent(issueID));
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const modal = document.getElementById("modal");
    const titleEl = document.getElementById("modal-title");
    const metaEl = document.getElementById("modal-meta");
    const issueEl = document.getElementById("modal-issue");
    const linkEl = document.getElementById("modal-link");
    const body = document.getElementById("modal-body");

    if (titleEl) titleEl.textContent = data.nameOfMeeting || "";
    if (metaEl) metaEl.textContent = `${data.date || ""} / 発言 ${(data.speeches || []).length} 件`;
    if (issueEl) issueEl.textContent = data.issueID || "";
    if (linkEl) {
      linkEl.href = (hintItem && hintItem.meetingURL) || `https://kokkai.ndl.go.jp/txt/${data.issueID || ""}`;
    }
    if (body) body.innerHTML = "";

    (data.speeches || []).forEach((sp, i) => {
      const div = document.createElement("div");
      div.className = "border-l-4 border-blue-200 pl-4 py-1";
      const safeSpeech = (sp.speech || "").replace(/</g, "&lt;");
      div.innerHTML = `
        <div class="flex justify-between">
          <div class="font-medium">${sp.speaker || "不明"} <span class="text-xs text-slate-400">(${sp.speechOrder || i+1})</span></div>
          <a href="${sp.speechURL || '#'}" target="_blank" class="text-blue-500 text-xs hover:underline">詳細</a>
        </div>
        <div class="speech text-slate-700 mt-1">${safeSpeech}</div>
      `;
      if (body) body.appendChild(div);
    });

    if (modal) {
      modal.classList.remove("hidden");
      modal.classList.add("flex");
    }
  } catch (e) {
    console.error(e);
    alert("会議録取得失攷: " + (e.message || e));
  } finally {
    showLoading(false);
  }
}

function hideModal() {
  const modal = document.getElementById("modal");
  if (modal) {
    modal.classList.remove("flex");
    modal.classList.add("hidden");
  }
}

function showLoading(show) {
  const loading = document.getElementById("loading");
  if (loading) {
    loading.classList.toggle("hidden", !show);
    loading.style.display = show ? "block" : "none";
  }
}

function nextPage() {
  if (!currentParams || Object.keys(currentParams).length === 0) return;
  const step = parseInt(currentParams.limit || "20");
  doSearch(currentStart + step);
}

function prevPage() {
  if (!currentParams || Object.keys(currentParams).length === 0) return;
  const step = parseInt(currentParams.limit || "20");
  const newStart = Math.max(1, currentStart - step);
  if (newStart !== currentStart) doSearch(newStart);
}

// Attach listeners and initial value
function initUI() {
  const searchBtn = document.getElementById("search-btn");
  const resetBtn = document.getElementById("reset-btn");

  if (searchBtn) {
    searchBtn.addEventListener("click", () => doSearch(1));
  }
  if (resetBtn) {
    resetBtn.addEventListener("click", resetForm);
  }

  // Prefill example query
  const queryEl = document.getElementById("query");
  if (queryEl && !queryEl.value) {
    queryEl.value = "生成AI";
  }

  console.log("Kokkai search UI initialized. Try clicking the search button.");
}

window.onload = initUI;
</script>
</body>
</html>""";


if __name__ == "__main__":
    import sys
    import socket

    # ポートを引数で上書き可能: python server.py 8080
    if len(sys.argv) > 1:
        try:
            PORT = int(sys.argv[1])
        except ValueError:
            print("ポート番号は整数で指定してください")
            sys.exit(1)

    # すべてのインターフェースで待ち受け（localhost と 127.0.0.1 の両対応）
    server_address = ("", PORT)

    try:
        httpd = HTTPServer(server_address, Handler)
    except OSError as e:
        if "address already in use" in str(e).lower() or e.errno in (98, 10048):
            print(f"エラー: ポート {PORT} はすでに使用されています。")
            print("別のポートで起動するには: python server.py 9000")
            print("または、すでに起動中のサーバーを止めてください。")
            sys.exit(1)
        raise

    print("=" * 55)
    print("✅ 国会議事録検索システム サーバー起動完了")
    print("")
    print("ブラウザで以下のどちらかを開いてください:")
    print(f"   http://localhost:{PORT}")
    print(f"   http://127.0.0.1:{PORT}")
    print("")
    print("⚠️  検索できない場合は:")
    print("   1. ブラウザで Ctrl + Shift + R (強制再読み込み)")
    print("   2. サーバーを再起動 (Ctrl+C → python server.py)")
    print("   3. F12 で開発者ツールを開き Console タブを確認")
    print("")
    print("サーバーを停止するには Ctrl + C を押してください")
    print("=" * 55)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しています...")
        httpd.server_close()
        print("終了しました。")
        sys.exit(0)
    except Exception as e:
        print(f"サーバーエラー: {e}")
        sys.exit(1)
"