import asyncio
from collections.abc import AsyncIterator, Sequence
from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic_ai import (
    AgentRunResultEvent,
    ModelMessage,
    ModelRequest,
    UsageLimitExceeded,
    UserPromptPart,
)
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_ai.usage import UsageLimits
from starlette.background import BackgroundTask
from sse_starlette import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.agent import build_message_history
from app.concurrency import (
    ConversationLease,
    try_acquire_conversation,
)
from app.database.core import Database
from app.database.dependencies import get_database
from app.llama import LlamaContextLimitCache
from app.web.dependencies import CurrentUserForUnsafeRequest, JsonRequest
from app.database.models import Conversation, Message, ModelMessageRecord
from app.model_history import serialize_model_messages
from app.observability.logging import get_logger
from app.observability.metrics import (
    record_llm_first_token,
    record_llm_stream_delta,
    record_llm_stream_duration,
    record_llm_stream_failure,
    record_conversation_lock_conflict,
    record_tool_calls_limit_exceeded,
)
from app.web.schemas import (
    ConversationMessageCreate,
    StreamDonePayload,
    StreamUsagePayload,
    ToolSelectedPayload,
)
from app.tools.tool_progress import capture_tool_selection_messages


router = APIRouter(prefix="/api/conversations")
logger = get_logger(__name__)
STREAM_ERROR_MESSAGE = "Unable to generate a response."
USAGE_LIMIT_ERROR_MESSAGE = "The assistant reached its execution limit."
TOOL_CALLS_LIMIT = 5
REQUEST_LIMIT = 8
TOOL_CALLS_LIMIT_MARKER = "tool_calls_limit"


def get_stream_agent():
    # The composition root owns the configured agent. Import lazily to avoid a
    # module cycle.
    from app.main import agent

    return agent


def get_context_limit_cache() -> LlamaContextLimitCache:
    from app.main import context_limit_cache

    return context_limit_cache


async def stream_persisted_message(
    database: Database,
    conversation_id: UUID,
    user_prompt: str,
    message_history: Sequence[ModelMessage],
    next_sequence: int,
    lease: ConversationLease,
) -> AsyncIterator[dict[str, str]]:
    try:
        try:
            response_parts: list[str] = []
            stream_started_at = perf_counter()
            first_token_at: float | None = None
            with capture_tool_selection_messages() as selection_messages:
                stream = get_stream_agent().run_stream_events(
                    user_prompt,
                    message_history=message_history,
                    usage_limits=UsageLimits(
                        tool_calls_limit=TOOL_CALLS_LIMIT,
                        request_limit=REQUEST_LIMIT,
                    ),
                )

                result = None
                async with stream as events:
                    async for event in events:
                        if isinstance(event, FunctionToolCallEvent):
                            message = selection_messages.get(event.part.tool_name)
                            if message is not None:
                                yield {
                                    "event": "tool_selected",
                                    "data": ToolSelectedPayload(
                                        message=message
                                    ).model_dump_json(),
                                }
                            continue

                        token: str | None = None
                        if isinstance(event, PartStartEvent) and isinstance(
                            event.part, TextPart
                        ):
                            token = event.part.content
                        elif isinstance(event, PartDeltaEvent) and isinstance(
                            event.delta, TextPartDelta
                        ):
                            token = event.delta.content_delta
                        elif isinstance(event, AgentRunResultEvent):
                            result = event.result

                        if token:
                            if first_token_at is None:
                                first_token_at = perf_counter()
                                ttft_seconds = first_token_at - stream_started_at
                                record_llm_first_token(ttft_seconds)
                                logger.info(
                                    "llm_first_token", ttft_ms=ttft_seconds * 1_000
                                )

                            record_llm_stream_delta()
                            response_parts.append(token)
                            yield {"data": token}

                if result is None:
                    raise RuntimeError("The model stream ended without a result.")

                new_message_payloads = serialize_model_messages(result.new_messages()[1:])
                record_llm_stream_duration(perf_counter() - stream_started_at)
                usage = result.usage
                done_payload = StreamDonePayload(
                    usage=StreamUsagePayload(
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        context_limit=await get_context_limit_cache().get_context_limit(),
                    )
                )
        except asyncio.CancelledError:
            raise
        except UsageLimitExceeded as error:
            record_llm_stream_failure()
            if TOOL_CALLS_LIMIT_MARKER in error.message:
                record_tool_calls_limit_exceeded()
            logger.info("message_stream_usage_limit_exceeded")
            yield {"event": "error", "data": USAGE_LIMIT_ERROR_MESSAGE}
            return
        except Exception:
            record_llm_stream_failure()
            logger.error("message_stream_failed")
            yield {"event": "error", "data": STREAM_ERROR_MESSAGE}
            return

        try:
            async with database.session_factory() as session:
                assistant_message = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content="".join(response_parts),
                )
                session.add(assistant_message)
                session.add_all(
                    ModelMessageRecord(
                        conversation_id=conversation_id,
                        sequence=next_sequence + offset,
                        payload=payload,
                    )
                    for offset, payload in enumerate(new_message_payloads)
                )
                await session.commit()

            yield {"event": "done", "data": done_payload.model_dump_json()}
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("message_stream_failed")
            yield {"event": "error", "data": STREAM_ERROR_MESSAGE}
    finally:
        await lease.release()


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    payload: ConversationMessageCreate,
    current_user: CurrentUserForUnsafeRequest,
    _: JsonRequest,
    database: Database = Depends(get_database),
) -> EventSourceResponse:
    try:
        async with database.session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == current_user.id,
                )
            )
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found.",
                )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.error("message_prepare_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to prepare message.",
        ) from exc

    if not await try_acquire_conversation(conversation_id):
        record_conversation_lock_conflict()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A message is already being generated for this conversation.",
        )

    lease = ConversationLease(conversation_id)
    ownership_transferred = False
    try:
        async with database.session_factory() as session:
            try:
                result = await session.scalars(
                    select(ModelMessageRecord)
                    .where(ModelMessageRecord.conversation_id == conversation_id)
                    .order_by(ModelMessageRecord.sequence.asc())
                )
                stored_model_messages = list(result)
                history = build_message_history(stored_model_messages)
                user_message_payload = serialize_model_messages(
                    [ModelRequest(parts=[UserPromptPart(payload.message)])]
                )[0]
                next_sequence = (
                    stored_model_messages[-1].sequence + 1
                    if stored_model_messages
                    else 0
                )

                session.add(
                    Message(
                        conversation_id=conversation_id,
                        role="user",
                        content=payload.message,
                    )
                )
                session.add(
                    ModelMessageRecord(
                        conversation_id=conversation_id,
                        sequence=next_sequence,
                        payload=user_message_payload,
                    )
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.error("message_prepare_failed")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to prepare message.",
                ) from exc

        response = EventSourceResponse(
            stream_persisted_message(
                database,
                conversation_id,
                payload.message,
                history,
                next_sequence + 1,
                lease,
            ),
            background=BackgroundTask(lease.release),
        )
        ownership_transferred = True
        return response
    finally:
        if not ownership_transferred:
            await lease.release()
