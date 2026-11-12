from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.announcements import (
    AnnouncementDiscoveryService,
    AnnouncementRecord,
    AnnouncementSourceError,
    BSEAnnouncementsAdapter,
    DemoAnnouncementAdapter,
    NSEAnnouncementsAdapter,
    RawAnnouncementDocumentStore,
    persist_announcement_batch,
)
from finn_api.db.models import (
    Announcement,
    Company,
    CompanyAlias,
    DataSource,
    SourceSyncState,
)


def test_nse_adapter_extracts_metadata_timestamps_and_primary_file_url() -> None:
    payload = [
        {
            "symbol": "RELIANCE",
            "seq_id": "nse-123",
            "an_dt": "10-11-2026 10:15:00",
            "desc": "Quarterly results filed",
            "attchmntFile": "/corporate/results.pdf",
        }
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        )
    )
    adapter = NSEAnnouncementsAdapter(client=client)

    records = adapter.fetch(date(2026, 11, 10), date(2026, 11, 10), "RELIANCE.NS")

    assert len(records) == 1
    assert records[0].source_key == "nse-123"
    assert records[0].ticker == "RELIANCE"
    assert records[0].filed_at.utcoffset().total_seconds() == 19800
    assert records[0].original_document_url == "https://www.nseindia.com/corporate/results.pdf"
    client.close()


def test_nse_month_name_timestamp_and_attachment_title_are_supported() -> None:
    payload = [
        {
            "symbol": "TCS",
            "seq_id": "nse-124",
            "an_dt": "10-Nov-2026 10:15:00",
            "attchmntText": "Investor presentation upload",
        }
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        )
    )
    records = NSEAnnouncementsAdapter(client=client).fetch(
        date(2026, 11, 10), date(2026, 11, 10)
    )

    assert len(records) == 1
    assert records[0].headline == "Investor presentation upload"
    assert records[0].filed_at.date() == date(2026, 11, 10)
    client.close()


def test_bse_adapter_extracts_bse_announcement() -> None:
    payload = [
        {
            "SCRIP_CD": "500001",
            "NEWSID": "bse-456",
            "DT_TM": "10/11/2026 11:15:00",
            "NEWSSUB": "Company disclosure",
            "NSURL": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/test.pdf",
        }
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        )
    )
    adapter = BSEAnnouncementsAdapter(client=client)

    records = adapter.fetch(date(2026, 11, 10), date(2026, 11, 10), "500001")

    assert len(records) == 1
    assert records[0].exchange == "BSE"
    assert records[0].ticker == "500001"
    assert records[0].original_document_url.endswith("test.pdf")
    client.close()


def test_source_rejects_unrecognized_json_shape() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"unexpected": []}, request=request)
        )
    )
    adapter = NSEAnnouncementsAdapter(client=client)

    with pytest.raises(AnnouncementSourceError, match="invalid_response_schema"):
        adapter.fetch(date(2026, 11, 10), date(2026, 11, 10))
    client.close()


def test_discovery_deduplicates_and_falls_back_to_explicit_demo_fixture() -> None:
    current_time = datetime(2026, 11, 10, 10, tzinfo=timezone.utc)
    record = AnnouncementRecord(
        source="nse_public_announcements",
        source_key="same-key",
        exchange="NSE",
        ticker="RELIANCE",
        headline="Filing",
        filed_at=current_time,
        source_url="https://www.nseindia.com/filing",
        original_document_url=None,
        fetched_at=current_time,
        payload_hash="hash",
        source_timestamp=current_time,
        raw_payload={"symbol": "RELIANCE"},
    )

    class DuplicateAdapter:
        source_name = "test_public_source"

        def fetch(self, start: date, end: date, ticker: str | None = None):
            return (record, record)

    fixture_adapter = DemoAnnouncementAdapter(
        Path(__file__).resolve().parents[1] / "data" / "fixtures" / "announcements.json"
    )
    batch = AnnouncementDiscoveryService(
        (DuplicateAdapter(),), demo_fallback=fixture_adapter
    ).discover(date(2026, 11, 10), date(2026, 11, 10))
    assert len(batch.records) == 1
    assert not batch.demo_used

    class UnavailableAdapter:
        source_name = "nse_public_announcements"

        def fetch(self, start: date, end: date, ticker: str | None = None):
            raise AnnouncementSourceError(self.source_name, "source_unavailable")

    fallback = AnnouncementDiscoveryService(
        (UnavailableAdapter(),), demo_fallback=fixture_adapter
    ).discover(date(2026, 11, 10), date(2026, 11, 10), "RELIANCE")
    assert fallback.demo_used
    assert len(fallback.records) == 1
    assert fallback.records[0].is_demo
    assert fallback.records[0].source == "demo_fixture"
    assert "[DEMO ONLY]" in fallback.records[0].headline


def test_original_document_store_only_accepts_bounded_exchange_pdfs(tmp_path) -> None:
    pdf = b"%PDF-1.4\nfixture"
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=pdf,
                headers={"content-type": "application/pdf"},
                request=request,
            )
        )
    )
    store = RawAnnouncementDocumentStore(tmp_path, client=client)

    stored = store.download("https://www.bseindia.com/filing.pdf")
    rejected = store.download("https://example.com/filing.pdf")

    assert stored.status == "stored"
    assert stored.path is not None
    assert stored.sha256 is not None
    assert Path(stored.path).read_bytes() == pdf
    assert rejected.status == "rejected"
    assert rejected.error_code == "untrusted_document_host"
    client.close()


def test_announcement_persistence_deduplicates_and_tracks_sync_status() -> None:
    engine = create_engine("sqlite://")
    for model in (Company, CompanyAlias, DataSource, Announcement, SourceSyncState):
        model.__table__.create(engine)
    with Session(engine) as session:
        company = Company(legal_name="Reliance Industries Limited", display_name="Reliance")
        session.add(company)
        session.flush()
        session.add(
            CompanyAlias(
                company_id=company.id,
                exchange="NSE",
                symbol="RELIANCE.NS",
                normalized_symbol="RELIANCE",
            )
        )
        session.commit()

        record = AnnouncementRecord(
            source="nse_public_announcements",
            source_key="nse-123",
            exchange="NSE",
            ticker="RELIANCE",
            headline="Filing",
            filed_at=datetime(2026, 11, 10, 10, tzinfo=timezone.utc),
            source_url="https://www.nseindia.com/filing.pdf",
            original_document_url="https://www.nseindia.com/filing.pdf",
            fetched_at=datetime(2026, 11, 10, 11, tzinfo=timezone.utc),
            payload_hash="hash",
            source_timestamp=datetime(2026, 11, 10, 10, tzinfo=timezone.utc),
            raw_payload={"symbol": "RELIANCE"},
            retrieval_status="stored",
            raw_document_path="C:/fixtures/hash.pdf",
        )
        from finn_api.data_pipeline.announcements import AnnouncementBatch, SourceRetrieval

        batch = AnnouncementBatch(
            records=(record,),
            source_retrievals=(
                SourceRetrieval(
                    source=record.source,
                    status="success",
                    fetched_at=record.fetched_at,
                    records_found=1,
                ),
            ),
        )

        assert persist_announcement_batch(session, batch) == 1
        assert persist_announcement_batch(session, batch) == 0
        saved = session.scalar(select(Announcement))
        sync = session.scalar(select(SourceSyncState))

        assert saved is not None
        assert saved.source_payload_hash == "hash"
        assert saved.raw_document_path == "C:/fixtures/hash.pdf"
        assert saved.retrieval_status == "stored"
        assert sync is not None and sync.status == "success"
    engine.dispose()
