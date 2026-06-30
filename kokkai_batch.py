#!/usr/bin/env python3
"""
Kokkai 検索 バッチ処理ヘルパースクリプト

テキストファイルに複数クエリを用意して一括で MD ファイルを生成します。
API サーバー負荷軽減のため、クエリごとに 1〜5 秒のランダムスリープを入れます。

機能:
- 並列度制限 (--workers)
- ログ出力 (--log-file)
- スリープ時間調整 (--sleep-min / --sleep-max)
- 日本語日付対応（cli.py 側で処理）

使い方:
  python kokkai_batch.py queries.txt
  python kokkai_batch.py queries.txt --workers 2 --log-file batch.log

queries.txt の例（一行に CLI 引数を記述。# でコメント可能）:

--query "生成AI" --speaker "岸田" --from "2024-01-01"
--query "デジタル" -s "上野" --from "1989年11月01日まで"
--query "AI規制" --from "2023年" --until "2025年12月31日"

注意:
- 各行は cli.py にそのまま渡す引数です。
- MD ファイルは cli.py の標準動作で自動生成されます。
- スリープは指定範囲のランダム（ polite to the National Diet Library API ）。
"""

import subprocess
import sys
import time
import random
import shlex
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_query(line, sleep_min, sleep_max, logger):
    """ 単一クエリを実行"""
    logger.info(f"Executing: python cli.py {line}")
    try:
        cmd = [sys.executable, "cli.py"] + shlex.split(line)
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        output = result.stdout.strip()
        if output:
            logger.info(output)
        if result.stderr:
            logger.warning(result.stderr.strip())
    except Exception as e:
        logger.error(f"Error executing query: {e}")

    # スリープ（最後のクエリ以外）
    sleep_time = random.uniform(sleep_min, sleep_max)
    logger.info(f"Sleeping for {sleep_time:.1f} seconds to avoid API overload...")
    time.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(
        description="Kokkai 検索 バッチ処理ヘルパー (MD自動生成 + レート制限)"
    )
    parser.add_argument("query_file", help="クエリ一覧テキストファイル")
    parser.add_argument("--workers", type=int, default=1,
                        help="並列実行数 (デフォルト: 1 = 逐次実行)")
    parser.add_argument("--log-file", help="ログ出力ファイル (省略時はコンソールのみ)")
    parser.add_argument("--sleep-min", type=float, default=1.0,
                        help="クエリ間最小スリープ秒 (デフォルト: 1)")
    parser.add_argument("--sleep-max", type=float, default=5.0,
                        help="クエリ間最大スリープ秒 (デフォルト: 5)")

    args = parser.parse_args()

    query_file = Path(args.query_file)
    if not query_file.exists():
        print(f"Error: File not found: {query_file}")
        sys.exit(1)

    # ログ設定
    logger = logging.getLogger("kokkai_batch")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # コンソールハンドラ
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # ファイルハンドラ（指定時）
    if args.log_file:
        fh = logging.FileHandler(args.log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.info(f"Logging to file: {args.log_file}")

    # クエリ読み込み
    with open(query_file, "r", encoding="utf-8") as f:
        lines = []
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)

    if not lines:
        logger.warning("No queries found in the file.")
        sys.exit(0)

    logger.info(f"Found {len(lines)} queries in {query_file}")
    logger.info(f"Workers: {args.workers}, Sleep: {args.sleep_min}~{args.sleep_max}s")

    # 並列実行
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for i, line in enumerate(lines):
            future = executor.submit(run_query, line, args.sleep_min, args.sleep_max, logger)
            futures.append(future)

        # 完了待ち（エラーはログに出る）
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error(f"Task failed: {e}")

    logger.info("Batch processing completed.")


if __name__ == "__main__":
    main()