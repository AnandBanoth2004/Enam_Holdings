from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

CopilotLayer = Literal["push", "pull", "network"]
CopilotIntent = Literal[
    "push_digest",
    "push_alert_explanation",
    "push_market_movement",
    "pull_research",
    "pull_financial_trajectory",
    "pull_guidance",
    "pull_cash_quality",
    "pull_financial_risks",
    "network_expertise",
    "network_company_connections",
    "network_executive_diligence",
    "cross_portfolio_context",
    "cross_company_context",
    "unsupported",
]


class CopilotQueryRequest(BaseModel):
    workspace_id: UUID
    query: str = Field(min_length=3, max_length=2000)
    conversation_id: UUID | None = None


class CopilotCitation(BaseModel):
    source_type: Literal["filing", "research_document", "market_data", "relationship", "alert"]
    title: str
    source_url: str | None = None
    ticker: str | None = None
    reporting_period: str | None = None
    page_number: int | None = None
    quote: str | None = None
    is_synthetic: bool = False


class CopilotAnswerBlock(BaseModel):
    layer: CopilotLayer
    heading: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    citations: list[CopilotCitation] = Field(default_factory=list)


class CopilotToolResult(BaseModel):
    name: str
    status: Literal["complete", "partial", "unavailable"]
    message: str


class CopilotQueryResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    query: str
    intent: CopilotIntent
    layers: list[CopilotLayer]
    answer: str
    blocks: list[CopilotAnswerBlock]
    tools: list[CopilotToolResult]
    limitations: list[str] = Field(default_factory=list)
    created_at: datetime


class CopilotConversationItem(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None


class CopilotMessageItem(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    result: CopilotQueryResponse | None = None
    created_at: datetime


class CopilotConversationList(BaseModel):
    conversations: list[CopilotConversationItem]


class CopilotConversationHistory(BaseModel):
    conversation_id: UUID
    messages: list[CopilotMessageItem]
