import argparse
import sys
from pathlib import Path

from app.crawler import esb_prices, legislators, tpex_prices, twse_prices
from app.crawler.base import Job, run_crawler
from app.crawler.declarations.csv_import import import_holdings, import_politicians
from app.db import SessionLocal

# 三個股價爬蟲
PRICE_JOBS: dict[str, Job] = {
    "twse_prices": twse_prices.job,
    "tpex_prices": tpex_prices.job,
    "esb_prices": esb_prices.job,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.crawler")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prices", help="抓上市＋上櫃＋興櫃股價")
    sub.add_parser("legislators", help="抓立法院第11屆立委名單")
    for name in PRICE_JOBS:
        sub.add_parser(name)
    for name in ("import_politicians", "import_holdings"):
        sub.add_parser(name).add_argument("csv", type=Path)
    args = parser.parse_args(argv)

    if args.command == "prices":
        jobs = dict(PRICE_JOBS)
    elif args.command == "legislators":
        jobs = {"legislators": legislators.job}
    elif args.command in PRICE_JOBS:
        jobs = {args.command: PRICE_JOBS[args.command]}
    elif args.command == "import_politicians":
        jobs = {args.command: lambda s: (import_politicians(s, args.csv), str(args.csv))}
    else:
        jobs = {args.command: lambda s: (import_holdings(s, args.csv), str(args.csv))}

    ok = True
    for name, job in jobs.items():
        log = run_crawler(SessionLocal, name, job)
        print(f"[{log.status}] {name}: {log.rows} 筆 {log.message or ''}")
        ok = ok and log.status == "success"
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
