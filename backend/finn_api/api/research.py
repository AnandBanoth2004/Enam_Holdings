from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, attributes

from finn_api.api.auth import get_current_user, require_workspace_membership

from finn_api.config import get_settings
from finn_api.data_pipeline.company_documents import (
    CompanyDocumentDiscoveryService,
    persist_company_documents,
)
from finn_api.data_pipeline.validation import normalize_nse_ticker
from finn_api.db.engine import get_db_session
from finn_api.db.models import (
    CompanyAlias,
    Document,
    ResearchCitation,
    ResearchReport,
    ResearchRun,
    User,
    Workspace,
)
from finn_api.pull.answering import AnswerGenerationError, generate_grounded_answer
from finn_api.pull.companies import resolve_company_and_website
from finn_api.pull.documents import (
    DocumentDownloadError,
    PrimaryDocumentDownloader,
)
from finn_api.pull.ingestion import ingest_primary_document
from finn_api.pull.financial_extraction import persist_document_financials
from finn_api.pull.financial_research import (
    build_financial_research_report,
    company_for_ticker,
    list_financial_periods,
    list_primary_sources,
    search_companies,
)
from finn_api.pull.pdf_processing import DocumentProcessingError
from finn_api.pull.providers import ModelProviderError, OpenAICompatibleProvider
from finn_api.pull.retrieval import DocumentRetriever, RetrievalCache
from finn_api.schemas.research import (
    ResearchAnswerRequest,
    ResearchAnswerResponse,
    ResearchDiscoveryRequest,
    ResearchDiscoveryResponse,
    ResearchDocumentItem,
    ResearchIngestionRequest,
    ResearchIngestionResponse,
)
from finn_api.schemas.financial_research import (
    CompanySearchResponse,
    FinancialExtractionRequest,
    FinancialExtractionResponse,
    FinancialMetricsResponse,
    FinancialResearchReportResponse,
    ResearchReportRequest,
    ResearchSection,
    ResearchSourceReference,
    ResearchSourcesResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["pull research"])
settings = get_settings()
retrieval_cache = RetrievalCache(ttl_seconds=settings.research_retrieval_cache_seconds)


def _provider() -> OpenAICompatibleProvider | None:
    if not settings.research_api_key:
        return None
    return OpenAICompatibleProvider(
        api_base_url=settings.research_api_base_url,
        api_key=settings.research_api_key,
        embedding_model=settings.embedding_model,
        research_model=settings.research_model,
        embedding_dimensions=settings.embedding_dimensions,
    )


def _research_error(
    status_code: int,
    code: str,
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _company_or_404(session: Session, ticker: str):
    normalized = normalize_nse_ticker(ticker)
    try:
        company, alias = company_for_ticker(session, normalized)
    except LookupError as error:
        raise _research_error(
            status.HTTP_404_NOT_FOUND,
            "company_not_discovered",
            str(error),
        ) from error
    return normalized, company, alias


def _financial_report(
    session: Session,
    *,
    ticker: str,
    company_id: UUID,
    reporting_basis: str,
    quarters: int = 4,
    persist_guidance: bool = False,
) -> FinancialResearchReportResponse:
    report = build_financial_research_report(
        session,
        company_id=company_id,
        ticker=ticker,
        reporting_basis=reporting_basis,
        quarters=quarters,
        persist_guidance=persist_guidance,
    )
    return FinancialResearchReportResponse.model_validate(report)


@router.post("/discover", response_model=ResearchDiscoveryResponse)
def discover_primary_documents(
    request: ResearchDiscoveryRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ResearchDiscoveryResponse:
    ticker = normalize_nse_ticker(request.ticker)
    try:
        company, issuer_website = resolve_company_and_website(session, ticker)
    except LookupError as error:
        raise _research_error(
            status.HTTP_404_NOT_FOUND,
            "issuer_unavailable",
            str(error),
        ) from error

    discovery = CompanyDocumentDiscoveryService()
    try:
        result = discovery.discover(
            ticker,
            issuer_website=issuer_website,
            allowed_document_hosts=settings.configured_document_hosts,
        )
    finally:
        discovery.close()
    persist_company_documents(session, result, company_id=company.id)
    documents = session.scalars(
        select(Document)
        .where(
            Document.company_id == company.id,
            Document.ingestion_status != "superseded",
            Document.source_url.in_(
                [item.source_url for item in result.documents] or [""]
            ),
        )
        .order_by(Document.document_type, Document.title)
    ).all()
    return ResearchDiscoveryResponse(
        ticker=ticker,
        company_name=company.display_name,
        status=result.status,
        fetched_at=result.fetched_at,
        error_code=result.error_code,
        documents=[
            ResearchDocumentItem(
                id=document.id,
                document_type=document.document_type,
                title=document.title,
                source_url=document.source_url,
                period_label=document.period_label,
                ingestion_status=document.ingestion_status,
                is_primary_source=document.is_primary_source,
                is_synthetic=document.synthetic,
            )
            for document in documents
            if document.document_type
            in {
                "annual_report",
                "quarterly_result",
                "earnings_call_transcript",
                "investor_presentation",
            }
        ],
    )


@router.post(
    "/documents/{document_id}/ingest",
    response_model=ResearchIngestionResponse,
)
def ingest_document(
    document_id: UUID,
    request: ResearchIngestionRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ResearchIngestionResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise _research_error(
            status.HTTP_404_NOT_FOUND,
            "document_not_found",
            "The requested company document was not found.",
        )
    alias = session.scalar(
        select(CompanyAlias)
        .where(
            CompanyAlias.company_id == document.company_id,
            CompanyAlias.exchange == "NSE",
        )
        .order_by(CompanyAlias.normalized_symbol)
        .limit(1)
    )
    if alias is None:
        raise _research_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "ticker_mapping_missing",
            "The document is not mapped to a supported NSE ticker.",
        )

    provider = _provider()
    downloader = PrimaryDocumentDownloader(
        max_file_bytes=settings.document_max_file_bytes
    )
    try:
        outcome = ingest_primary_document(
            session,
            document=document,
            ticker=alias.normalized_symbol,
            downloader=downloader,
            storage_directory=settings.data_directory / "documents",
            embedding_provider=provider,
            trusted_document_hosts=settings.configured_document_hosts,
            embedding_dimensions=settings.embedding_dimensions,
            expected_period=request.expected_period,
            max_chunk_tokens=request.max_chunk_tokens,
        )
    except DocumentDownloadError as error:
        code = 422 if error.code.startswith(("untrusted_", "unsupported_", "invalid_")) else 502
        raise _research_error(code, error.code, str(error)) from error
    except DocumentProcessingError as error:
        raise _research_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            error.code,
            str(error),
        ) from error
    except ModelProviderError as error:
        raise _research_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            error.code,
            str(error),
        ) from error
    finally:
        downloader.close()
        if provider:
            provider.close()

    retrieval_cache.clear()
    return ResearchIngestionResponse(
        document_id=outcome.document_id,
        status=outcome.status,
        duplicate_of=outcome.duplicate_of,
        page_count=outcome.page_count,
        chunk_count=outcome.chunk_count,
        embedded_chunk_count=outcome.embedded_chunk_count,
        embedding_model=outcome.embedding_model,
        extraction_method=outcome.extraction_method,
        period_label=outcome.period_label,
    )


@router.get("/companies/search", response_model=CompanySearchResponse)
def search_company_universe(
    q: str,
    limit: int = 20,
    session: Session = Depends(get_db_session),
) -> CompanySearchResponse:
    try:
        results = search_companies(session, q, limit=limit)
    except ValueError as error:
        raise _research_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_company_search",
            str(error),
        ) from error
    return CompanySearchResponse(query=q.strip(), results=results)


@router.post(
    "/documents/{document_id}/extract-financials",
    response_model=FinancialExtractionResponse,
)
def extract_document_financials(
    document_id: UUID,
    request: FinancialExtractionRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> FinancialExtractionResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise _research_error(
            status.HTTP_404_NOT_FOUND,
            "document_not_found",
            "The requested company document was not found.",
        )
    try:
        outcome = persist_document_financials(
            session,
            document=document,
            period_label=request.period_label,
            period_start=request.period_start,
            period_end=request.period_end,
            period_type=request.period_type,
            reporting_basis=request.reporting_basis,
            currency=request.currency,
            unit_scale=request.unit_scale,
        )
        session.commit()
    except ValueError as error:
        session.rollback()
        raise _research_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "financial_extraction_rejected",
            str(error),
        ) from error
    return FinancialExtractionResponse(
        document_id=document.id,
        period_id=outcome.period_id,
        period_label=request.period_label,
        reporting_basis=request.reporting_basis,
        extracted_count=len(outcome.extracted),
        metric_keys=[item.metric_key for item in outcome.extracted],
        ambiguous_metric_keys=list(outcome.ambiguous_metric_keys),
        values={item.metric_key: item.value for item in outcome.extracted},
    )


@router.get("/companies/{ticker}/financial-metrics", response_model=FinancialMetricsResponse)
def get_company_financial_metrics(
    ticker: str,
    reporting_basis: str = "consolidated",
    session: Session = Depends(get_db_session),
) -> FinancialMetricsResponse:
    normalized, company, _ = _company_or_404(session, ticker)
    try:
        periods = list_financial_periods(session, company.id, reporting_basis)
    except ValueError as error:
        raise _research_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_reporting_basis",
            str(error),
        ) from error
    return FinancialMetricsResponse(
        ticker=normalized,
        reporting_basis=reporting_basis,
        periods=periods,
    )


@router.get("/companies/{ticker}/report", response_model=FinancialResearchReportResponse)
def get_latest_company_report(
    ticker: str,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> FinancialResearchReportResponse:
    require_workspace_membership(session, workspace_id=workspace_id, user=user)
    normalized, company, _ = _company_or_404(session, ticker)
    report = session.scalar(
        select(ResearchReport)
        .where(
            ResearchReport.workspace_id == workspace_id,
            ResearchReport.company_id == company.id,
            ResearchReport.is_synthetic.is_(False),
        )
        .order_by(ResearchReport.created_at.desc())
        .limit(1)
    )
    if report is None or report.content is None:
        raise _research_error(
            status.HTTP_404_NOT_FOUND,
            "research_report_not_found",
            "No saved primary-source research report exists for this company and workspace.",
        )
    return FinancialResearchReportResponse.model_validate(report.content)


@router.post("/companies/{ticker}/report", response_model=FinancialResearchReportResponse)
def create_company_research_report(
    ticker: str,
    request: ResearchReportRequest,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> FinancialResearchReportResponse:
    require_workspace_membership(
        session,
        workspace_id=request.workspace_id,
        user=user,
    )
    normalized, company, _ = _company_or_404(session, ticker)
    workspace = session.get(Workspace, request.workspace_id)
    if workspace is None:
        raise _research_error(
            status.HTTP_404_NOT_FOUND,
            "workspace_not_found",
            "The requested workspace does not exist.",
        )
    try:
        report = build_financial_research_report(
            session,
            company_id=company.id,
            ticker=normalized,
            reporting_basis=request.reporting_basis,
            quarters=request.quarters,
            persist_guidance=True,
        )
    except ValueError as error:
        session.rollback()
        raise _research_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_research_request",
            str(error),
        ) from error
    prompt_version = "financial-research-v1"
    run = session.scalar(
        select(ResearchRun).where(
            ResearchRun.workspace_id == workspace.id,
            ResearchRun.requested_ticker == normalized,
            ResearchRun.prompt_version == prompt_version,
        )
    )
    if run is None:
        run = ResearchRun(
            workspace_id=workspace.id,
            requested_ticker=normalized,
            company_id=company.id,
            status=report["status"],
            model_route=report["model_route"],
            prompt_version=prompt_version,
            is_synthetic=False,
        )
        session.add(run)
        session.flush()
    run.company_id = company.id
    run.status = report["status"]
    run.completed_at = report["generated_at"]
    run.model_route = report["model_route"]
    run.source_manifest = [
        ResearchSourceReference.model_validate(item).model_dump(mode="json")
        for item in report["source_manifest"]
    ]
    report_key = f"financial-research-{normalized.casefold()}-v1"
    saved_report = session.scalar(
        select(ResearchReport).where(
            ResearchReport.workspace_id == workspace.id,
            ResearchReport.report_key == report_key,
        )
    )
    response_payload = FinancialResearchReportResponse.model_validate(report).model_dump(
        mode="json"
    )
    if saved_report is None:
        saved_report = ResearchReport(
            workspace_id=workspace.id,
            company_id=company.id,
            research_run_id=run.id,
            report_key=report_key,
            title=f"{company.display_name} financial research",
            status=report["status"],
            summary="Deterministic analysis of available primary-source financial data.",
            content=None,
            source_manifest=run.source_manifest,
            model_route=report["model_route"],
            prompt_version=prompt_version,
            is_synthetic=False,
        )
        session.add(saved_report)
        session.flush()
    else:
        saved_report.company_id = company.id
        saved_report.research_run_id = run.id
        saved_report.status = report["status"]
        saved_report.content = response_payload
        saved_report.source_manifest = run.source_manifest
        saved_report.model_route = report["model_route"]
        saved_report.prompt_version = prompt_version
        saved_report.is_synthetic = False
    response_payload["report_id"] = str(saved_report.id)
    saved_report.content = dict(response_payload)
    run.result = dict(response_payload)
    attributes.flag_modified(saved_report, "content")
    attributes.flag_modified(run, "result")
    session.execute(
        delete(ResearchCitation).where(ResearchCitation.research_run_id == run.id)
    )
    for section_name in (
        "business_snapshot",
        "financial_snapshot",
        "financial_trajectory",
        "balance_sheet_analysis",
        "cash_quality_analysis",
        "narrative_vs_numbers",
        "management_guidance",
        "bull_vs_bear",
    ):
        section = report[section_name]
        for claim_type in ("facts", "calculations", "interpretations"):
            for index, claim in enumerate(section[claim_type]):
                for citation_index, citation in enumerate(claim["citations"]):
                    if not citation.get("chunk_id") or not citation.get("quote"):
                        continue
                    session.add(
                        ResearchCitation(
                            research_run_id=run.id,
                            chunk_id=citation["chunk_id"],
                            claim_key=f"{section_name}:{claim_type}:{index}:{citation_index}",
                            page_start=citation.get("page_number"),
                            page_end=citation.get("page_number"),
                            quoted_text=citation["quote"],
                            source_url=citation["source_url"],
                            is_synthetic=False,
                        )
                    )
    session.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return FinancialResearchReportResponse.model_validate(response_payload)


@router.get("/companies/{ticker}/financial-trajectory", response_model=ResearchSection)
def get_financial_trajectory(
    ticker: str,
    reporting_basis: str = "consolidated",
    session: Session = Depends(get_db_session),
) -> ResearchSection:
    normalized, company, _ = _company_or_404(session, ticker)
    try:
        report = _financial_report(
            session,
            ticker=normalized,
            company_id=company.id,
            reporting_basis=reporting_basis,
        )
    except ValueError as error:
        raise _research_error(422, "invalid_reporting_basis", str(error)) from error
    return report.financial_trajectory


@router.get("/companies/{ticker}/guidance")
def get_management_guidance(
    ticker: str,
    quarters: int = 4,
    reporting_basis: str = "consolidated",
    session: Session = Depends(get_db_session),
) -> dict:
    normalized, company, _ = _company_or_404(session, ticker)
    if not 1 <= quarters <= 4:
        raise _research_error(422, "invalid_quarter_count", "quarters must be between 1 and 4.")
    try:
        report = _financial_report(
            session,
            ticker=normalized,
            company_id=company.id,
            reporting_basis=reporting_basis,
            quarters=quarters,
        )
    except ValueError as error:
        raise _research_error(422, "invalid_reporting_basis", str(error)) from error
    return report.management_guidance.model_dump(mode="json")


@router.get("/companies/{ticker}/narrative-comparison")
def get_narrative_comparison(
    ticker: str,
    quarters: int = 4,
    reporting_basis: str = "consolidated",
    session: Session = Depends(get_db_session),
) -> dict:
    normalized, company, _ = _company_or_404(session, ticker)
    if not 1 <= quarters <= 4:
        raise _research_error(422, "invalid_quarter_count", "quarters must be between 1 and 4.")
    try:
        report = _financial_report(
            session,
            ticker=normalized,
            company_id=company.id,
            reporting_basis=reporting_basis,
            quarters=quarters,
        )
    except ValueError as error:
        raise _research_error(422, "invalid_reporting_basis", str(error)) from error
    return report.narrative_vs_numbers.model_dump(mode="json")


@router.get("/companies/{ticker}/bull-bear", response_model=ResearchSection)
def get_bull_bear_analysis(
    ticker: str,
    reporting_basis: str = "consolidated",
    session: Session = Depends(get_db_session),
) -> ResearchSection:
    normalized, company, _ = _company_or_404(session, ticker)
    try:
        report = _financial_report(
            session,
            ticker=normalized,
            company_id=company.id,
            reporting_basis=reporting_basis,
        )
    except ValueError as error:
        raise _research_error(422, "invalid_reporting_basis", str(error)) from error
    return report.bull_vs_bear


@router.get("/companies/{ticker}/sources", response_model=ResearchSourcesResponse)
def get_research_sources(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> ResearchSourcesResponse:
    normalized, company, _ = _company_or_404(session, ticker)
    return ResearchSourcesResponse(
        ticker=normalized,
        sources=list_primary_sources(session, company.id),
    )


@router.post("/answer", response_model=ResearchAnswerResponse)
def answer_research_question(
    request: ResearchAnswerRequest,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ResearchAnswerResponse:
    ticker = normalize_nse_ticker(request.ticker)
    alias = session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.exchange == "NSE",
            CompanyAlias.normalized_symbol == ticker,
        )
    )
    if alias is None:
        raise _research_error(
            status.HTTP_404_NOT_FOUND,
            "company_not_discovered",
            "Discover primary documents for this NSE ticker before requesting research.",
        )

    provider = _provider()
    try:
        retriever = DocumentRetriever(
            embedding_provider=provider,
            cache=retrieval_cache,
            max_context_chars=settings.research_max_context_chars,
        )
        evidence = retriever.retrieve(
            session,
            company_id=alias.company_id,
            ticker=ticker,
            query=request.question,
            document_types=tuple(request.document_types),
            period_start=request.period_start,
            period_end=request.period_end,
            top_k=request.top_k,
            include_synthetic=request.include_synthetic,
        )
        answer = generate_grounded_answer(
            ticker=ticker,
            question=request.question,
            evidence=evidence,
            research_model=provider,
        )
    except ModelProviderError as error:
        raise _research_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            error.code,
            str(error),
        ) from error
    except AnswerGenerationError as error:
        raise _research_error(
            status.HTTP_502_BAD_GATEWAY,
            "citation_validation_failed",
            str(error),
        ) from error
    finally:
        if provider:
            provider.close()
    response.headers["Cache-Control"] = "private, no-store"
    return ResearchAnswerResponse.model_validate(answer.model_dump())
