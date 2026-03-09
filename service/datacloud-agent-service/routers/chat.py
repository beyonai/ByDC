"""Chat completion routes (OpenAI compatible).

Provides POST /v1/chat/completions endpoint with support for both
streaming and non-streaming responses.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from deps import TenantAwareGatewayClient

router = APIRouter()


class ChatMessage(BaseModel):
    """A single chat message (OpenAI format)."""

    role: str = Field(..., description="The role of the message sender")
    content: str = Field(..., description="The content of the message")


class ChatCompletionRequest(BaseModel):
    """Request for chat completion (OpenAI compatible)."""

    messages: list[ChatMessage] = Field(
        ..., description="A list of messages comprising the conversation"
    )
    model: str | None = Field(
        default=None,
        description="The model to use (agent ID). If not provided, uses default agent.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for continuing a conversation",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response",
    )
    temperature: float | None = Field(
        default=None,
        description="Sampling temperature (not used in this implementation)",
    )
    max_tokens: int | None = Field(
        default=None,
        description="Maximum tokens to generate (not used in this implementation)",
    )


class ChatCompletionResponseChoice(BaseModel):
    """A single choice in the chat completion response."""

    index: int = Field(default=0, description="The index of the choice")
    message: ChatMessage = Field(..., description="The generated message")
    finish_reason: str | None = Field(default=None, description="Reason for finishing")


class ChatCompletionResponse(BaseModel):
    """Non-streaming chat completion response (OpenAI compatible)."""

    id: str = Field(..., description="Unique identifier for the completion")
    object: str = Field(default="chat.completion", description="Object type")
    created: int = Field(..., description="Unix timestamp of creation")
    model: str = Field(..., description="Model (agent) used")
    choices: list[ChatCompletionResponseChoice] = Field(
        ..., description="List of completion choices"
    )
    usage: dict[str, Any] | None = Field(default=None, description="Token usage information")


class ChatCompletionStreamResponseChunk(BaseModel):
    """Streaming response chunk (OpenAI compatible)."""

    id: str = Field(..., description="Unique identifier for the completion")
    object: str = Field(default="chat.completion.chunk", description="Object type")
    created: int = Field(..., description="Unix timestamp of creation")
    model: str = Field(..., description="Model (agent) used")
    choices: list[dict[str, Any]] = Field(
        ..., description="List of completion choices for this chunk"
    )


@router.post("/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    gateway_client: TenantAwareGatewayClient,
    http_request: Request,
):
    """Create a chat completion (supports both streaming and non-streaming).

    This endpoint is compatible with the OpenAI Chat Completions API.
    If stream=True is specified, the response will be streamed using SSE.

    Args:
        request: The chat completion request
        gateway_client: Gateway client instance
        http_request: The HTTP request object (for extracting headers)

    Returns:
        Either ChatCompletionResponse (JSON) or StreamingResponse (SSE)

    Raises:
        HTTPException: If there's an error processing the request
    """
    # Extract the last user message (simplified - we only support single turn for now)
    user_messages = [msg for msg in request.messages if msg.role in ("user", "system")]
    if not user_messages:
        raise HTTPException(
            status_code=400,
            detail="At least one user or system message is required",
        )
    # Use the last user message as the prompt
    last_message = user_messages[-1]
    prompt = last_message.content

    # Determine agent ID (model) and session ID
    agent_id = request.model or "default"
    session_id = request.session_id

    # Generate common ID and timestamp
    completion_id = f"chatcmpl-{int(time.time())}"
    created = int(time.time())

    if request.stream:
        # Streaming response
        async def generate_stream() -> AsyncIterator[str]:
            """Generate SSE stream chunks."""
            try:
                # Get streaming response from gateway client
                async for chunk in gateway_client.chat_stream(
                    message=prompt,
                    session_id=session_id,
                    agent_id=agent_id,
                ):
                    # Build OpenAI-compatible chunk
                    response_chunk = ChatCompletionStreamResponseChunk(
                        id=completion_id,
                        created=created,
                        model=agent_id,
                        choices=[
                            {
                                "index": 0,
                                "delta": {"content": chunk.content},
                                "finish_reason": "stop" if chunk.is_last else None,
                            }
                        ],
                    )
                    yield f"data: {response_chunk.model_dump_json()}\n\n"

                # Send [DONE] marker
                yield "data: [DONE]\n\n"
            except Exception as e:
                # Send error as SSE event
                error_event = {
                    "error": str(e),
                    "id": completion_id,
                }
                yield f"data: {json.dumps(error_event)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # Non-streaming response
        try:
            # Call the gateway client
            response = await gateway_client.chat(
                message=prompt,
                session_id=session_id,
                agent_id=agent_id,
                stream=False,
            )

            # Build OpenAI-compatible response
            return ChatCompletionResponse(
                id=completion_id,
                created=created,
                model=agent_id,
                choices=[
                    ChatCompletionResponseChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=response.content,
                        ),
                        finish_reason="stop",
                    )
                ],
                usage={
                    "prompt_tokens": 0,  # Not implemented
                    "completion_tokens": 0,  # Not implemented
                    "total_tokens": 0,
                },
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
