#!/usr/bin/env python3
"""
Kokkai レポート生成モジュール (stdlib のみ)

- Markdown レポート生成
- HTML レポート生成（ブラウザで開いて PDF 保存用）
- ファイル作成とブラウザ起動機能

CLI から呼び出して使用可能。
"""

import datetime
import html
import os
import re
import tempfile
import webbrowser
from typing import Any, Dict, List


def _sanitize_for_filename(s: str) -> str:
    """\u30d5ァイル名用に安全な文字列に変換"""
    if not s:
        return ""
    # \u7121効文字を _ に置換、日本語・英数字・-は保持
    s = re.sub(r'[\\/:*?"<>|\t ]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:40]


def generate_markdown(
    items: List[Dict[str, Any]], 
    params: Dict[str, Any], 
    total: int = None
) -> str:
    """\u691c索結果から Markdown 文字列を生成"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = []

    lines.append("# 国会議事録検索結果")
    lines.append("")
    lines.append("## 検索条件")
    lines.append(f"- キーワード: {params.get('query') or '（指定なし）'}")
    lines.append(f"- 発言者: {params.get('speaker') or '（指定なし）'}")
    lines.append(f"- 会議名: {params.get('nameOfMeeting') or '（指定なし）'}")
    lines.append(f"- 期間: {params.get('from', '') or ''} 〜 {params.get('until', '') or ''}")
    lines.append(f"- 取得上限: {params.get('limit', 10)} 件")
    lines.append(f"- 出力日時: {now}")
    if total is not None:
        lines.append(f"- 総ヒット数: {total}")
    lines.append("")
    lines.append("## 発言一覧")
    lines.append("")

    for i, item in enumerate(items, 1):
        date = item.get("date", "日付不明")
        speaker = item.get("speaker", "発言者不明")
        meeting = item.get("nameOfMeeting", "")
        speech = item.get("speech", "").replace("\r\n", "\n")
        speech_url = item.get("speechURL", "")
        meeting_url = item.get("meetingURL", "")

        lines.append(f"### 【{i}】 {date} - {speaker}")
        if meeting:
            lines.append(f"**\u4f1a議**: {meeting}")
        lines.append("")
        lines.append("**\u672c文**:")
        lines.append(speech)
        lines.append("")
        if speech_url:
            lines.append(f"**\u767a言URL**: {speech_url}")
        if meeting_url:
            lines.append(f"**\u4f1a議録URL**: {meeting_url}")
        lines.append("")

    return "\n".join(lines)


def generate_html_report(
    items: List[Dict[str, Any]], 
    params: Dict[str, Any], 
    total: int = None
) -> str:
    """\u30d6ラウザ印刷用 HTML を生成（PDF 保存向け）"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def esc(s: str) -> str:
        return html.escape(s or "")

    cond_html = f"""
    <h2>\u691c索条件</h2>
    <ul>
      <li>\u30adーワード: {esc(params.get('query') or '（指定なし）')}</li>
      <li>\u767a言者: {esc(params.get('speaker') or '（指定なし）')}</li>
      <li>\u4f1a議名: {esc(params.get('nameOfMeeting') or '（指定なし）')}</li>
      <li>\u671f間: {esc(params.get('from', ''))} 〜 {esc(params.get('until', ''))}</li>
      <li>\u53d6得上限: {params.get('limit', 10)} 件</li>
    </ul>
    <p>\u51fa力日時: {esc(now)} / \u30d2ット: {total if total is not None else len(items)} 件</p>
    """

    item_blocks = []
    for i, item in enumerate(items, 1):
        date = esc(item.get("date", ""))
        speaker = esc(item.get("speaker", ""))
        meeting = esc(item.get("nameOfMeeting", ""))
        speech = esc(item.get("speech", "")).replace("\n", "<br>")
        speech_url = item.get("speechURL", "")
        meeting_url = item.get("meetingURL", "")

        block = f"""
        <div style="page-break-inside: avoid; margin-bottom: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.8em;">
          <h3>\u3010{i}\u3011 {date} - {speaker}</h3>
          <p><strong>\u4f1a議</strong>: {meeting}</p>
          <p><strong>\u672c文</strong></p>
          <div style="white-space: pre-wrap; background:#f8f8f8; padding:8px; border-left:3px solid #ccc;">
            {speech}
          </div>
          <p><strong>\u767a言URL</strong>: <a href="{speech_url}">{speech_url}</a></p>
          <p><strong>\u4f1a議録URL</strong>: <a href="{meeting_url}">{meeting_url}</a></p>
        </div>
        """
        item_blocks.append(block)

    html_doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>\u56fd会議事録検索結果</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 40px auto; line-height: 1.6; font-size: 11pt; }}
  h1 {{ border-bottom: 2px solid #333; }}
  h2 {{ font-size: 14pt; }}
  @media print {{
    body {{ padding: 0; font-size: 10pt; }}
    .no-print {{ display: none !important; }}
  }}
  a {{ color: #0066cc; word-break: break-all; }}
</style>
</head>
<body>
<h1>\u56fd会議事録検索結果</h1>

{cond_html}

<h2>\u767a言一覧</h2>

{''.join(item_blocks)}

<div class="no-print" style="margin-top: 2em; padding: 1em; background: #f0f0f0; border-radius: 6px;">
  <button onclick="window.print()" style="padding: 8px 16px; font-size: 12pt; background:#059669; color:white; border:none; border-radius:4px; cursor:pointer;">
    \u3053のページをPDFとして保存（\u5370刷ダイアログで\u300cPDFとして保存\u300dを選択）
  </button>
  <p style="margin: 8px 0 0; font-size: 9pt;">\u30d6ラウザの印刷機能を使ってPDFファイルに変換してください。</p>
</div>

<p style="margin-top: 2em; font-size: 9pt; color: #777; border-top: 1px solid #ddd; padding-top: 8px;">
  \u672c資料は国立国会図書館\u300c\u56fd会議事録検索システムAPI\u300d\u3092利用して生成しました\u3002
</p>
</body>
</html>"""
    return html_doc


def create_md_file(
    items: List[Dict[str, Any]], 
    params: Dict[str, Any], 
    total: int = None,
    filename: str = None
) -> str:
    """\u73fe在の作業ディレクトリに MD ファイルを作成してパスを返す"""
    if filename is None:
        date_str = datetime.date.today().strftime("%Y%m%d")
        q = _sanitize_for_filename(params.get("query", ""))
        s = _sanitize_for_filename(params.get("speaker", ""))
        f = _sanitize_for_filename(params.get("from", "") or "")
        filename = f"{date_str}-{q}-{s}-{f}.md".replace("--", "-").strip("-")

    md_content = generate_markdown(items, params, total)
    path = os.path.join(os.getcwd(), filename)

    with open(path, "w", encoding="utf-8") as fp:
        fp.write(md_content)

    return path


def open_in_browser_for_pdf(
    items: List[Dict[str, Any]], 
    params: Dict[str, Any], 
    total: int = None
) -> str:
    """
    HTML レポートを一時ファイルに書き、ブラウザで開く。
    \u30e6ーザーはブラウザの印刷機能で PDF 保存可能。
    """
    html_content = generate_html_report(items, params, total)

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".html", mode="w", encoding="utf-8"
    ) as f:
        f.write(html_content)
        tmp_path = f.name

    file_url = "file://" + os.path.abspath(tmp_path)
    webbrowser.open(file_url)

    print(f"\u30d6ラウザで\u30ecポートを開きました: {tmp_path}")
    print("\u30d6ラウザ上で Ctrl+P \u2192 \u300cPDF\u3068して保存\u300dを選択してください。")
    return tmp_path


def _sanitize_for_filename(s: str) -> str:
    if not s: return ""
    s = re.sub(r'[\\/:*?"<>| \t]', '_', s)
    s = re.sub(r'_+', '_', s)
    return s[:40]

if __name__ == "__main__":
    print("kokkai_report: \u30e2ジュールとして使用してください。")
    print("  from kokkai_report import create_md_file, open_in_browser_for_pdf")