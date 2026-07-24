# Tool Progress and Reliability Design

## Purpose

Complete the remaining success conditions of issue #16 while showing a concise, user-facing indication when the model selects a tool.

## User-Facing Tool Progress Contract

The server adds one SSE event:

```text
event: tool_selected
data: {"message":"현재 날씨를 확인하고 있어요."}
```

- It is emitted when the model has selected a function tool and before that tool executes.
- The frontend shows the message until it receives the first response text, `done`, or `error`.
- There are no separate completed or failed progress events. The final response or existing error flow is the single source of truth for those outcomes.
- The event does not contain tool arguments, raw tool names, results, or provider details.

## Tool-Owned Presentation Metadata

Each MCP tool declares its own optional plain-text progress message in FastMCP `meta`:

```python
meta={"my_ai_assistant": {"selection_message": "..."}}
```

Pydantic AI preserves MCP `meta` in `ToolDefinition.metadata`. The generic agent execution path reads this namespaced metadata without recognizing particular tool names. A new tool therefore opts into progress display by declaring its own metadata; the chat router and frontend require no per-tool conditionals.

Metadata is external input. The generic reader accepts only a bounded plain string and sends it as text, never HTML. Missing or invalid metadata means no progress event.

## Failure Semantics

The MCP metric wrapper records a timeout with outcome `timeout`, then raises a generic `ToolError`. Pydantic AI can return that failure to the model as a retry prompt, giving the model an opportunity to explain it naturally. Tool-call and request limits retain their existing terminal SSE error behavior.

## Toolset Availability

Toolset activation reports a generic success or failure state to the composition root. The composition root sets:

```text
mcp_toolset_up{toolset="weather"} = 1 | 0
```

This is a static, bounded label. It describes startup availability only; it does not add provider-specific latency or result-content telemetry. The Grafana dashboard displays the current availability.

## Verification

- A model tool-call event with valid tool metadata emits one `tool_selected` event before text output.
- Invalid or absent metadata emits no event and never leaks tool arguments or names.
- A timeout is recorded as `timeout` and becomes a model-retryable tool error.
- Successful and failed activation set the availability gauge to 1 and 0 respectively.
- `/metrics` and Grafana include all four issue metrics.
- Existing SSE, message-persistence, lint, type, and regression tests remain green.
