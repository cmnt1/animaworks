# -*- coding: utf-8 -*-
"""Run repo-managed report generation jobs from runtime wrappers or cron."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

JOBS = {
    "anjo-1k-daily": "core.reports.property.anjo_1k_product_draft",
    "daily-sale-info": "core.reports.property.daily_sale_product_report",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an AnimaWorks report job.")
    parser.add_argument("--job", required=True, choices=sorted(JOBS))
    parser.add_argument("--report-date")
    parser.add_argument("--task-results-dir", type=Path)
    return parser.parse_args(argv)


def build_job_args(args: argparse.Namespace) -> list[str]:
    job_args: list[str] = []
    if args.report_date:
        job_args.extend(["--report-date", args.report_date])
    if args.task_results_dir:
        job_args.extend(["--task-results-dir", str(args.task_results_dir)])
    return job_args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    module = importlib.import_module(JOBS[args.job])
    if not hasattr(module, "main"):
        print(json.dumps({"status": "blocked", "reason": "job_main_missing", "job": args.job}))
        return 1
    return int(module.main(build_job_args(args)))


if __name__ == "__main__":
    raise SystemExit(main())
