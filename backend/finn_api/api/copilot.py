from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finn_api.api.auth import get_current_user, require_workspace_membership
from finn_api.copilot.service import execute_query, save_exchange
from finn_api.db.engine import get_db_session
from finn_api.db.models import CopilotConversation, CopilotMessage, User, Workspace
from finn_api.schemas.copilot import (
    CopilotConversationHistory,
    CopilotConversationItem,
    CopilotConversationList,
    CopilotMessageItem,
    CopilotQueryRequest,
    CopilotQueryResponse,
)

router = APIRouter(
    prefix="/copilot",
    tags=["research copilot"],
    dependencies=[Depends(get_current_user)],
)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "copilot_conversation_not_found",
            "message": "The requested Copilot conversation was not found for this user and workspace.",
        },
    )


@router.post("/query", response_model=CopilotQueryResponse)
def ask_copilot(
    request: CopilotQueryRequest,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> CopilotQueryResponse:
    require_workspace_membership(
        session,
        workspace_id=request.workspace_id,
        user=user,
    )
    if session.get(Workspace, request.workspace_id) is None:
        raise _not_found()
    try:
        plan, answer, blocks, tools, limitations = execute_query(
            session,
            workspace_id=request.workspace_id,
            query=request.query,
        )
    except LookupError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "copilot_source_not_found", "message": str(error)},
        ) from error
    response_data = {
        "conversation_id": (
            str(request.conversation_id) if request.conversation_id else None
        ),
        "message_id": str(UUID(int=0)),
        "query": request.query,
        "intent": plan.intent,
        "layers": list(plan.layers),
        "answer": answer,
        "blocks": [item.model_dump(mode="json") for item in blocks],
        "tools": [item.model_dump(mode="json") for item in tools],
        "limitations": limitations,
    }
    try:
        conversation, assistant_message = save_exchange(
            session,
            user=user,
            workspace_id=request.workspace_id,
            query=request.query,
            conversation_id=request.conversation_id,
            response_data=response_data,
        )
    except LookupError as error:
        session.rollback()
        raise _not_found() from error
    response_data["conversation_id"] = conversation.id
    response_data["message_id"] = assistant_message.id
    response_data["created_at"] = assistant_message.created_at
    assistant_message.result = CopilotQueryResponse.model_validate(response_data).model_dump(
        mode="json"
    )
    session.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return CopilotQueryResponse.model_validate(response_data)


@router.get("/conversations", response_model=CopilotConversationList)
def list_copilot_conversations(
    workspace_id: UUID,
    response: Response,
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> CopilotConversationList:
    require_workspace_membership(
        session,
        workspace_id=workspace_id,
        user=user,
    )
    latest_messages = (
        select(
            CopilotMessage.conversation_id.label("conversation_id"),
            CopilotMessage.content.label("content"),
            func.row_number()
            .over(
                partition_by=CopilotMessage.conversation_id,
                order_by=(CopilotMessage.created_at.desc(), CopilotMessage.id.desc()),
            )
            .label("message_rank"),
        )
        .subquery()
    )
    rows = session.execute(
        select(CopilotConversation, latest_messages.c.content)
        .outerjoin(
            latest_messages,
            (latest_messages.c.conversation_id == CopilotConversation.id)
            & (latest_messages.c.message_rank == 1),
        )
        .where(
            CopilotConversation.workspace_id == workspace_id,
            CopilotConversation.user_id == user.id,
        )
        .order_by(CopilotConversation.updated_at.desc())
        .limit(limit)
    ).all()
    items = []
    for row, last_message_content in rows:
        items.append(
            CopilotConversationItem(
                id=row.id,
                title=row.title,
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_message_preview=(
                    last_message_content[:180] if last_message_content else None
                ),
            )
        )
    response.headers["Cache-Control"] = "private, no-store"
    return CopilotConversationList(conversations=items)


@router.get(
    "/conversations/{conversation_id}",
    response_model=CopilotConversationHistory,
)
def get_copilot_conversation(
    conversation_id: UUID,
    workspace_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> CopilotConversationHistory:
    require_workspace_membership(
        session,
        workspace_id=workspace_id,
        user=user,
    )
    conversation = session.scalar(
        select(CopilotConversation).where(
            CopilotConversation.id == conversation_id,
            CopilotConversation.workspace_id == workspace_id,
            CopilotConversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise _not_found()
    messages = session.scalars(
        select(CopilotMessage)
        .where(CopilotMessage.conversation_id == conversation.id)
        .order_by(CopilotMessage.created_at, CopilotMessage.id)
    ).all()
    response.headers["Cache-Control"] = "private, no-store"
    return CopilotConversationHistory(
        conversation_id=conversation.id,
        messages=[
            CopilotMessageItem(
                id=message.id,
                role=message.role,
                content=message.content,
                result=(
                    CopilotQueryResponse.model_validate(message.result)
                    if message.role == "assistant" and message.result
                    else None
                ),
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_copilot_conversation(
    conversation_id: UUID,
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> None:
    require_workspace_membership(
        session,
        workspace_id=workspace_id,
        user=user,
    )
    conversation = session.scalar(
        select(CopilotConversation).where(
            CopilotConversation.id == conversation_id,
            CopilotConversation.workspace_id == workspace_id,
            CopilotConversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise _not_found()
    session.delete(conversation)
    session.commit()
