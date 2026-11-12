from __future__ import annotations

import logging
from urllib.parse import urlparse

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.orm import Session

from finn_api.data_pipeline.validation import normalize_nse_ticker
from finn_api.db.models import Company, CompanyAlias

logger = logging.getLogger(__name__)


def _company_profile(ticker: str) -> dict[str, object]:
    try:
        profile = yf.Ticker(f"{ticker}.NS").get_info()
    except Exception as error:
        logger.warning(
            "Issuer profile lookup failed ticker=%s error_type=%s",
            ticker,
            type(error).__name__,
        )
        raise LookupError(
            f"Issuer metadata is unavailable for NSE ticker {ticker}."
        ) from error
    if not isinstance(profile, dict):
        raise LookupError(f"Issuer metadata is unavailable for NSE ticker {ticker}.")
    returned_symbol = profile.get("symbol")
    if isinstance(returned_symbol, str):
        try:
            if normalize_nse_ticker(returned_symbol) != ticker:
                raise LookupError("Issuer profile resolved to a different NSE ticker.")
        except ValueError as error:
            raise LookupError("Issuer profile returned an unsupported ticker.") from error
    return profile


def resolve_company_and_website(
    session: Session,
    ticker: str,
) -> tuple[Company, str]:
    symbol = normalize_nse_ticker(ticker)
    alias = session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.exchange == "NSE",
            CompanyAlias.normalized_symbol == symbol,
        )
    )
    profile = _company_profile(symbol)
    website = profile.get("website")
    if not isinstance(website, str):
        raise LookupError(
            f"No issuer website is available for NSE ticker {symbol}."
        )
    website_url = website if "://" in website else f"https://{website}"
    parsed_website = urlparse(website_url)
    if parsed_website.scheme != "https" or not parsed_website.hostname:
        raise LookupError(
            f"The issuer website for NSE ticker {symbol} is not a valid HTTPS URL."
        )

    if alias is not None:
        company = session.get(Company, alias.company_id)
        if company is None:
            raise LookupError(f"The company mapped to NSE ticker {symbol} was not found.")
        return company, parsed_website.geturl()

    display_name = profile.get("longName") or profile.get("shortName")
    if not isinstance(display_name, str) or not display_name.strip():
        raise LookupError(
            f"Company identity could not be verified for NSE ticker {symbol}."
        )
    name = display_name.strip()[:240]
    company = session.scalar(select(Company).where(Company.legal_name == name))
    if company is None:
        company = Company(
            legal_name=name,
            display_name=name[:180],
            synthetic=False,
        )
        session.add(company)
        session.flush()
    session.add(
        CompanyAlias(
            company_id=company.id,
            exchange="NSE",
            symbol=symbol,
            normalized_symbol=symbol,
            alias=name,
            synthetic=False,
        )
    )
    session.commit()
    return company, parsed_website.geturl()
