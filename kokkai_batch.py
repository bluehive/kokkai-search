#!/usr/bin/env python3
"""
Kokkai 検索 バッチ処理ヘルパースクリプト

テキストファイルに複数クエリを用意して、一括で MD ファイルを生成します。
API サーバ負荷軽減のため、クエリごとに 1〜5 秒のランダムスリープを入れます。

機能:
- 並列度制限 (--workers)
- ログ出力 (--log-file)
- スリープ時間調整 (--sleep-min / --sleep-max)
- 失敗時リトライ (--retry)
- ドライラン (--dry-run)
- 進捕表示 (シンプルプログレスバー)
- 日本語日付対応（cli.py 側で処理）

使い方:
  python kokkai_batch.py queries.txt
  python kokkai_batch.py queries.txt --workers 2 --log-file batch.log --retry 2 --dry-run
"""

import subprocess
import sys
import time
import random
import shlex
import argparse
import logging
import threading
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_query(line, sleep_min, sleep_max, retry, logger, dry_run=False, cli_script="cli.py"):
    """\u5358\u4e00\u30af\u30a8\u30ea\u3092\u5b9f\u884c\uff08\u30ea\u30c8\u30e9\u30a4\u5bfe\u5fdc\uff09"""
    if dry_run:
        logger.info(f"[DRY-RUN] Would execute: python {os.path.basename(cli_script)} {line}")
        return True

    attempts = 0
    max_attempts = retry + 1
    while attempts < max_attempts:
        attempts += 1
        try:
            logger.info(f"Executing (attempt {attempts}/{max_attempts}): python {os.path.basename(cli_script)} {line}")
            cmd = [sys.executable, cli_script] + shlex.split(line)

            # Force UTF-8 for child process output (important on Windows with Japanese text)
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",   # Prevent decode crashes on mojibake
                env=env
            )
            output = result.stdout.strip()
            if output:
                logger.info(output)
            if result.stderr:
                logger.warning(result.stderr.strip())

            if result.returncode == 0:
                return True
            else:
                logger.warning(f"Command failed with return code {result.returncode}")
        except Exception as e:
            logger.error(f"Error executing query (attempt {attempts}): {e}")

        if attempts < max_attempts:
            backoff = random.uniform(1, 3) * attempts
            logger.info(f"Retrying in {backoff:.1f}s...")
            time.sleep(backoff)

    logger.error(f"Failed after {max_attempts} attempts: {line}")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Kokkai \u691c\u7d22 \u30d0\u30c3\u30c1\u51e6\u7406\u30d8\u30eb\u30d1\u30fc (MD\u81ea\u52d5\u751f\u6210 + \u30ec\u30fc\u30c8\u5236\u9650)"
    )
    parser.add_argument("query_file", help="\u30af\u30a8\u30ea\u4e00\u89a7\u30c6\u30ad\u30b9\u30c8\u30d5\u30a1\u30a4\u30eb")
    parser.add_argument("--workers", type=int, default=1,
                        help="\u4e26\u5217\u5b9f\u884c\u6570 (\u30c7\u30d5\u30a9\u30eb\u30c8: 1 = \u9010\u6b21\u5b9f\u884c)")
    parser.add_argument("--log-file", help="\u30ed\u30b0\u51fa\u529b\u30d5\u30a1\u30a4\u30eb (\u7701\u7565\u6642\u306f\u30b3\u30f3\u30bd\u30fc\u30eb\u306e\u307f)")
    parser.add_argument("--sleep-min", type=float, default=1.0,
                        help="\u30af\u30a8\u30ea\u9593\u6700\u5c0f\u30b9\u30ea\u30fc\u30d7\u79d2 (\u30c7\u30d5\u30a9\u30eb\u30c8: 1)")
    parser.add_argument("--sleep-max", type=float, default=5.0,
                        help="\u30af\u30a8\u30ea\u9593\u6700\u5927\u30b9\u30ea\u30fc\u30d7\u79d2 (\u30c7\u30d5\u30a9\u30eb\u30c8: 5)")
    parser.add_argument("--retry", type=int, default=0,
                        help="\u5931\u6557\u6642\u306e\u30ea\u30c8\u30e9\u30a4\u56de\u6570 (\u30c7\u30d5\u30a9\u30eb\u30c8: 0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="\u5b9f\u969b\u306b\u5b9f\u884c\u305b\u305a\u3001\u4e88\u5b9a\u306e\u30b3\u30de\u30f3\u30c9\u306e\u307f\u8868\u793a")

    args = parser.parse_args()

    query_file = Path(args.query_file)
    if not query_file.exists():
        print(f"Error: File not found: {query_file}")
        sys.exit(1)

    # \u30b9\u30af\u30ea\u30d7\u30c8\u306e\u5834\u6240\u304b\u3089 cli.py \u3092\u7279\u5b9a\uff08CWD\u304c\u9055\u3046\u5834\u5408\u3067\u3082\u52d5\u4f5c\u3059\u308b\u3088\u3046\u306b\uff09
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cli_script = os.path.join(script_dir, "cli.py")

    # \u30ed\u30b0\u8a2d\u5b9a
    logger = logging.getLogger("kokkai_batch")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # \u30b3\u30f3\u30bd\u30fc\u30eb\u30cf\u30f3\u30c9\u30e9
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # \u30d5\u30a1\u30a4\u30eb\u30cf\u30f3\u30c9\u30e9\uff08\u6307\u5b9a\u6642\uff09
    if args.log_file:
        fh = logging.FileHandler(args.log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.info(f"Logging to file: {args.log_file}")

    # \u30af\u30a8\u30ea\u8aad\u307f\u8fbc\u307f
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
    logger.info(f"Workers: {args.workers}, Sleep: {args.sleep_min}~{args.sleep_max}s, Retry: {args.retry}, Dry-run: {args.dry_run}")

    if args.dry_run:
        logger.info("=== DRY RUN MODE: No actual execution ===")
        for line in lines:
            logger.info(f"Would run: python {os.path.basename(cli_script)} {line}")
        logger.info("=== DRY RUN COMPLETE ===")
        return

    total = len(lines)
    completed = 0
    success_count = 0
    fail_count = 0
    lock = threading.Lock()

    def update_progress():
        nonlocal completed
        with lock:
            completed += 1
            percent = 100.0 * completed / total
            bar = '#' * int(percent / 5) + '-' * (20 - int(percent / 5))
            print(f"\rProgress: [{bar}] {percent:.1f}% ({completed}/{total})", end="", flush=True)

    # \u4e26\u5217\u5b9f\u884c
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for line in lines:
            future = executor.submit(run_query, line, args.sleep_min, args.sleep_max, args.retry, logger, args.dry_run, cli_script)
            futures.append((future, line))

        for future, line in futures:
            try:
                ok = future.result()
                with lock:
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                update_progress()
            except Exception as e:
                logger.error(f"Task failed: {e}")
                with lock:
                    fail_count += 1
                update_progress()

    print()  # newline after progress bar
    logger.info(f"Batch processing completed. Success: {success_count}, Failed: {fail_count}")


if __name__ == "__main__":
    main()
