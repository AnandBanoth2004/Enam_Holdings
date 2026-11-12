import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

repository_root = Path(__file__).resolve().parents[1]
backend_dir = repository_root / "backend"
sys.path.insert(0, str(backend_dir))

from finn_api.config import get_settings  # noqa: E402
from finn_api.data_pipeline.announcements import (  # noqa: E402
    AnnouncementDiscoveryService,
    BSEAnnouncementsAdapter,
    DemoAnnouncementAdapter,
    NSEAnnouncementsAdapter,
    RawAnnouncementDocumentStore,
)
from finn_api.db.engine import SessionLocal  # noqa: E402
from finn_api.push.service import process_announcement_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover public NSE/BSE corporate announcements (not live market data)."
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--ticker", help="Optional company ticker or BSE scrip code.")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must be on or before --end")

    settings = get_settings()
    nse = NSEAnnouncementsAdapter()
    bse = BSEAnnouncementsAdapter()
    document_store = RawAnnouncementDocumentStore(settings.data_directory / "documents")
    try:
        service = AnnouncementDiscoveryService(
            (nse, bse),
            demo_fallback=DemoAnnouncementAdapter(
                settings.data_directory / "fixtures" / "announcements.json"
            ),
            document_store=document_store,
        )
        batch = service.discover(args.start, args.end, args.ticker)
    finally:
        nse.close()
        bse.close()
        document_store.close()

    with SessionLocal() as session:
        processed = process_announcement_batch(session, batch)
    for retrieval in batch.source_retrievals:
        print(
            f"{retrieval.source}: {retrieval.status}; records={retrieval.records_found}; "
            f"error={retrieval.error_code or '-'}"
        )
    print(
        f"Announcements processed={len(batch.records)}; inserted={processed['inserted']}; "
        f"classified={processed['classified']}; alerts={processed['alerts_created']}; "
        f"demo_fallback={batch.demo_used}"
    )


if __name__ == "__main__":
    main()
