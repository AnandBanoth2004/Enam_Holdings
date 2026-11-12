import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

repository_root = Path(__file__).resolve().parents[1]
backend_dir = repository_root / "backend"
sys.path.insert(0, str(backend_dir))

from finn_api.config import get_settings  # noqa: E402
from finn_api.data_pipeline.market_data import MarketDataService  # noqa: E402
from finn_api.data_pipeline.market_repository import SQLAlchemyMarketRepository  # noqa: E402
from finn_api.db.engine import SessionLocal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache NSE EOD market bars.")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--tickers",
        help="Comma-separated symbols; defaults to FINN_MARKET_TICKERS.",
    )
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must be on or before --end")

    settings = get_settings()
    tickers = (
        tuple(symbol.strip().upper() for symbol in args.tickers.split(",") if symbol.strip())
        if args.tickers
        else settings.configured_market_tickers
    )
    if not tickers:
        parser.error("Configure at least one ticker.")

    failed = 0
    with SessionLocal() as session:
        service = MarketDataService(
            cache=SQLAlchemyMarketRepository(session),
            cache_ttl=timedelta(seconds=settings.market_cache_ttl_seconds),
        )
        results = service.fetch_many(list(tickers), args.start, args.end)
        for ticker, result in results.items():
            print(
                f"{ticker}: {result.status}; rows={len(result.data)}; "
                f"source={result.source}; fetched_at={result.fetched_at.isoformat()}; "
                f"error={result.error_code or '-'}"
            )
            failed += result.status == "failed"
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
