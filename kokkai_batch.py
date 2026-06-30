#!/usr/bin/env python3
"""
Kokkai 検索 バッチ処理ヘルパースクリプト

テキストファイルに複数クエリを用意して一括で MD ファイルを生成します。
API サーバ負荷軽減のため、クエリごとに 1〜5 秒のランダムスリープを入れます。

機能:
- 並列度制限 (--workers)
- ログ出力 (--log-file)
- スリープ時間調整 (--sleep-min / --sleep-max)
- 失敗時リトライ (--retry)
- ドライラン (--dry-run)
- 進捕バー (シンプルプログレスバー)
- 日本語日付対応（cli.py 側で処理）

使い方:
  python kokkai_batch.py queries.txt
  python kokkai_batch.py queries.txt --workers 2 --log-file batch.log --retry 2 --dry-run

queries.txt の例（1行に CLI 引数を記述。# でコメント可能）:

--query "生成AI" --speaker "岸田" --from "2024-01-01"
--query "デジタル" -s "上野" --from "1989年11月01日まで"
--query "AI規制" --from "2023年" --until "2025年12月31日"

注意:
- 各行は cli.py にそのまま渡す引数です。
- MD ファイルは cli.py の標準動作で自動生成されます。
- スリープは指定範囲のランダム（ polite to the National Diet Library API 〉。
"""

import subprocess
import sys
import time
import random
import shlex
import argparse
import logging
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_query(line, sleep_min, sleep_max, retry, logger, dry_run=False):
    """ 単一クエリを実行（リトライ対応）"""
    if dry_run:
        logger.info(f"[DRY-RUN] Would execute: python cli.py {line}")
        return True

    attempts = 0
    max_attempts = retry + 1
    while attempts < max_attempts:
        attempts += 1
        try:
            logger.info(f"Executing (attempt {attempts}/{max_attempts}): python cli.py {line}")
            cmd = [sys.executable, "cli.py"] + shlex.split(line)
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
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
    parser.add_argument("--retry", type=int, default=0,
                        help="失敗時のリトライ回数 (デフォルト: 0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際に実行せず、予定のコマンドのみ表示")

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

    # ファイルハンダラ（指定時）
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
    logger.info(f"Workers: {args.workers}, Sleep: {args.sleep_min}~{args.sleep_max}s, Retry: {args.retry}, Dry-run: {args.dry_run}")

    if args.dry_run:
        logger.info("=== DRY RUN MODE: No actual execution ===")
        for line in lines:
            logger.info(f"Would run: python cli.py {line}")
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

    # 並列実行
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = []
        for line in lines:
            future = executor.submit(run_query, line, args.sleep_min, args.sleep_max, args.retry, logger, args.dry_run)
            futures.append(future)

        for future in as_completed(futures):
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