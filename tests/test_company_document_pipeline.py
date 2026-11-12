import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.company_documents import (
    CompanyDocumentDiscoveryService,
    WebsiteResolution,
    persist_company_documents,
)
from finn_api.db.models import Company, Document, SourceSyncState


def test_discovery_follows_issuer_ir_links_and_classifies_primary_documents() -> None:
    pages = {
        "https://issuer.example/": (
            '<a href="/investors">Investor relations</a>'
            '<a href="https://research.example/annual-report.pdf">Annual Report</a>'
        ),
        "https://issuer.example/investors": (
            '<a href="/files/annual-report-2025.pdf">Annual Report 2025</a>'
            '<a href="/files/quarterly-results-q2.pdf">Quarterly Results Q2</a>'
            '<a href="/files/q3-fy26-results.pdf">Q3 FY26 Results</a>'
            '<a href="/files/earnings-call-transcript.html">Earnings Call Transcript</a>'
            '<a href="/files/agm-transcript.pdf">Transcript of the 49th AGM</a>'
            '<a href="/investors/financial-reporting/webcast-transcript">'
            "Chairman's Statement</a>"
            '<a href="/files/investor-presentation.pdf">Investor Presentation</a>'
        ),
        "https://issuer.example/investors/financial-reporting/webcast-transcript": (
            "<p>Chairman's Statement</p>"
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/agm-transcript.pdf"):
            return httpx.Response(
                200,
                content=b"%PDF-demo",
                headers={"content-type": "application/pdf"},
                request=request,
            )
        body = pages.get(str(request.url))
        if body is None:
            return httpx.Response(404, request=request)
        return httpx.Response(
            200,
            text=body,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = CompanyDocumentDiscoveryService(client=client)
    result = service.discover("ARBITRARY", issuer_website="https://issuer.example/")

    types = {document.document_type for document in result.documents}
    urls = {document.source_url for document in result.documents}
    assert result.ticker == "ARBITRARY"
    assert result.status == "success"
    assert types == {
        "annual_report",
        "quarterly_result",
        "earnings_call_transcript",
        "investor_presentation",
    }
    assert all(document.is_primary_source for document in result.documents)
    assert not any("research.example" in url for url in urls)
    assert not any("agm-transcript" in url for url in urls)
    assert not any("webcast-transcript" in url for url in urls)
    assert all(document.source_name == "issuer.example" for document in result.documents)
    client.close()


def test_missing_issuer_site_is_explicitly_unavailable() -> None:
    class NoIssuerSite:
        def resolve(self, ticker: str) -> WebsiteResolution:
            return WebsiteResolution(None, "test_resolver")

    service = CompanyDocumentDiscoveryService(website_resolver=NoIssuerSite())
    result = service.discover("NEWCO")

    assert result.status == "unavailable"
    assert result.error_code == "issuer_website_not_found"
    assert result.documents == ()


def test_document_persistence_is_idempotent() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text='<a href="/annual-report.pdf">Annual Report</a>',
                headers={"content-type": "text/html"},
                request=request,
            )
        )
    )
    result = CompanyDocumentDiscoveryService(client=client).discover(
        "ARBITRARY", issuer_website="https://issuer.example/"
    )

    engine = create_engine("sqlite://")
    Company.__table__.create(engine)
    Document.__table__.create(engine)
    SourceSyncState.__table__.create(engine)
    with Session(engine) as session:
        company = Company(legal_name="Example Limited", display_name="Example")
        session.add(company)
        session.commit()
        assert persist_company_documents(session, result, company_id=company.id) == 1
        assert persist_company_documents(session, result, company_id=company.id) == 0
        saved = session.scalar(select(Document))
        assert saved is not None
        assert saved.document_type == "annual_report"
        assert saved.source_url == "https://issuer.example/annual-report.pdf"
    client.close()
    engine.dispose()
