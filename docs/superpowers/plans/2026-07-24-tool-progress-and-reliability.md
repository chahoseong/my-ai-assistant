# Tool Progress and Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream tool-owned progress safely, convert MCP timeouts to model-retryable errors, and expose toolset startup availability.

**Architecture:** FastMCP tools own optional `my_ai_assistant.selection_message` metadata. A generic wrapper resolves only safe metadata from `ToolDefinition.metadata`; the chat event loop emits it without naming any tool. The generic registration runtime reports availability to the FastAPI composition root, which owns the gauge.

**Tech Stack:** FastAPI SSE, Pydantic AI, FastMCP, Prometheus, React, TypeScript, Grafana.

## Global Constraints

- Add only `tool_selected`; text, `done`, and `error` clear progress.
- Never send tool names, arguments, provider responses, raw metadata, or HTML to the browser.
- Accept only trimmed plain messages of at most 120 characters.
- Preserve usage limits, persistence, cancellation, and existing terminal errors.

---

### Task 1: Tool-owned progress metadata

**Files:** Create `backend/app/tools/tool_progress.py`, `backend/tests/tools/test_tool_progress.py`; modify `backend/app/tools/weather_server.py`, `backend/app/tools/weather_toolset.py`, `backend/tests/tools/test_weather_server.py`.

**Interfaces:** `selection_message_from_metadata(metadata: object) -> str | None`; `ToolProgressToolset` derives a per-run `Mapping[str, str]` from `ToolsetTool.tool_def.metadata`.

- [ ] **Step 1: Write failing validation tests**

```python
assert selection_message_from_metadata({"meta": {"my_ai_assistant": {"selection_message": "현재 날씨를 확인하고 있어요."}}}) == "현재 날씨를 확인하고 있어요."
assert selection_message_from_metadata({"meta": {"my_ai_assistant": {"selection_message": "x" * 121}}}) is None
assert selection_message_from_metadata(None) is None
```

- [ ] **Step 2: Verify RED**

Run: `dotenvx run -- uv run pytest tests/tools/test_tool_progress.py -q`

Expected: FAIL because `tool_progress` does not exist.

- [ ] **Step 3: Implement the generic boundary**

```python
def selection_message_from_metadata(metadata: object) -> str | None:
    if not isinstance(metadata, Mapping): return None
    meta = metadata.get("meta")
    progress = meta.get("my_ai_assistant") if isinstance(meta, Mapping) else None
    message = progress.get("selection_message") if isinstance(progress, Mapping) else None
    if not isinstance(message, str): return None
    message = message.strip()
    return message if 0 < len(message) <= 120 else None
```

`ToolProgressToolset.get_tools()` delegates to its wrapped toolset and records valid messages by tool name. `for_run()` returns a fresh wrapper.

- [ ] **Step 4: Put status messages on the tools**

```python
@mcp.tool(meta={"my_ai_assistant": {"selection_message": "현재 날씨를 확인하고 있어요."}})
async def get_current_weather(...): ...
```

Declare the equivalent daily-forecast message on `get_daily_forecast`; wrap the existing guidance toolset with `ToolProgressToolset`, without a name-to-message map.

- [ ] **Step 5: Verify GREEN and commit**

Run: `dotenvx run -- uv run pytest tests/tools/test_tool_progress.py tests/tools/test_weather_server.py -q`

Expected: PASS, including MCP tool metadata assertions.

Commit: `git add backend/app/tools/tool_progress.py backend/app/tools/weather_server.py backend/app/tools/weather_toolset.py backend/tests/tools/test_tool_progress.py backend/tests/tools/test_weather_server.py && git commit -m "feat: add tool-owned progress metadata"`

### Task 2: Stream selected-tool progress

**Files:** Modify `backend/app/routers/chat.py`, `backend/app/web/schemas.py`, `backend/tests/conversations/test_message_streaming.py`, `backend/tests/web/test_stream_schemas.py`.

**Interfaces:** `ToolSelectedPayload(message: str)` serializes as `event: tool_selected`; the router consumes Pydantic AI `FunctionToolCallEvent`, text `PartDeltaEvent`, and `AgentRunResultEvent`.

- [ ] **Step 1: Write failing SSE tests**

```python
assert event_json(body, "tool_selected") == {"message": "현재 날씨를 확인하고 있어요."}
assert body.index("event: tool_selected") < body.index("data: final answer")
assert "get_current_weather" not in body
assert "서울" not in body
```

Use a fake event-stream agent with a selected tool, a text delta, and a final run result. Add a missing-metadata case that has no `tool_selected` event.

- [ ] **Step 2: Verify RED**

Run: `dotenvx run -- uv run pytest tests/conversations/test_message_streaming.py tests/web/test_stream_schemas.py -q`

Expected: FAIL because the event and event-based runner do not exist.

- [ ] **Step 3: Implement generic dispatch**

```python
if isinstance(event, FunctionToolCallEvent):
    if message := selection_messages.get(event.part.tool_name):
        yield {"event": "tool_selected", "data": ToolSelectedPayload(message=message).model_dump_json()}
```

Replace `run_stream().stream_text()` with `run_stream_events()`. Preserve text delta metrics, TTFT, `new_messages()`, usage, persistence, limits, and lease release. Do not add completion/failure progress events.

- [ ] **Step 4: Verify GREEN and commit**

Run: `dotenvx run -- uv run pytest tests/conversations/test_message_streaming.py tests/conversations/test_message_failures.py tests/web/test_stream_schemas.py -q`

Expected: PASS.

Commit: `git add backend/app/routers/chat.py backend/app/web/schemas.py backend/tests/conversations/test_message_streaming.py backend/tests/web/test_stream_schemas.py && git commit -m "feat: stream selected tool progress"`

### Task 3: Render progress in the existing pending bubble

**Files:** Modify `frontend/src/lib/sse.ts`, `frontend/src/components/ChatView.tsx`, `frontend/src/components/ChatView.css`.

**Interfaces:** Extend `StreamEvent` with `{ event: 'tool_selected'; data: { message: string } }` and `StreamSession` with `toolSelectionMessage: string | null`.

- [ ] **Step 1: Verify RED through TypeScript**

Reference `streamEvent.data.message` in a `tool_selected` branch before implementing its parser.

Run: `npm run build`

Expected: FAIL because `consumeEvent()` has no new union variant.

- [ ] **Step 2: Parse, display, and clear state**

```typescript
if (streamEvent.event === 'tool_selected') session.toolSelectionMessage = streamEvent.data.message
if (streamEvent.event === 'data' || streamEvent.event === 'done' || streamEvent.event === 'error') session.toolSelectionMessage = null
```

Validate JSON `message` as nonempty and at most 120 characters. Render it in the existing pending bubble, preserving animation and accessibility; clear it on cancellation and cleanup.

- [ ] **Step 3: Verify GREEN, browser behavior, and commit**

Run: `npm run lint; npm run build`

Expected: both PASS.

Browser check: “내일 서울 비가 올까?” shows the daily message before text and clears on first text without showing a tool name or city argument.

Commit: `git add frontend/src/lib/sse.ts frontend/src/components/ChatView.tsx frontend/src/components/ChatView.css && git commit -m "feat: show selected tool progress"`

### Task 4: Repair timeout and availability success conditions

**Files:** Modify `backend/app/tools/mcp_metrics.py`, `backend/app/observability/metrics.py`, `backend/app/tools/runtime.py`, `backend/app/main.py`, `backend/infra/observability/grafana/dashboards/assistant-observability.json`, `backend/tests/tools/test_mcp_metrics.py`, `backend/tests/tools/test_toolset_registry.py`, `backend/tests/observability/test_observability.py`, `backend/tests/observability/test_dashboard.py`.

**Interfaces:** `TimeoutError` becomes `ToolError("The tool timed out.")` after outcome `timeout`; `set_mcp_toolset_up(toolset: str, is_up: bool)` owns `Gauge("mcp_toolset_up", labelnames=("toolset",))`; activation accepts optional `report_availability(name: str, is_up: bool)`.

- [ ] **Step 1: Write failing tests**

```python
with pytest.raises(ToolError, match="The tool timed out"):
    await record_mcp_tool_call(...)
assert tool_call_count(outcome="timeout") == before + 1
assert states == [("failed", False), ("successful", True)]
```

Require `mcp_toolset_up` in the metrics registry and a Grafana `Toolset availability` panel querying `mcp_toolset_up{job="my-ai-assistant"}`.

- [ ] **Step 2: Verify RED**

Run: `dotenvx run -- uv run pytest tests/tools/test_mcp_metrics.py tests/tools/test_toolset_registry.py tests/observability/test_observability.py tests/observability/test_dashboard.py -q`

Expected: FAIL because timeout is re-raised and the gauge/callback/panel do not exist.

- [ ] **Step 3: Implement the bounded contracts**

```python
except TimeoutError:
    outcome = "timeout"
    raise ToolError("The tool timed out.") from None
```

Report `False` on activation failure and `True` on success; pass `set_mcp_toolset_up` from `main.lifespan`. Keep Prometheus imports out of generic runtime code.

- [ ] **Step 4: Verify GREEN and commit**

Run: `dotenvx run -- uv run pytest tests/tools/test_mcp_metrics.py tests/tools/test_toolset_registry.py tests/observability/test_observability.py tests/observability/test_dashboard.py -q`

Expected: PASS.

Commit: `git add backend/app/tools/mcp_metrics.py backend/app/observability/metrics.py backend/app/tools/runtime.py backend/app/main.py backend/infra/observability/grafana/dashboards/assistant-observability.json backend/tests/tools/test_mcp_metrics.py backend/tests/tools/test_toolset_registry.py backend/tests/observability/test_observability.py backend/tests/observability/test_dashboard.py && git commit -m "fix: make tool failures and availability observable"`

### Task 5: Complete issue verification

**Files:** Modify `README.md`, `backend/README.md`.

- [ ] **Step 1: Document the opt-in contract**

Document `my_ai_assistant.selection_message`, its no-metadata fallback, and `mcp_toolset_up` as startup availability.

- [ ] **Step 2: Run all checks**

```bash
dotenvx run -- uv run ruff check .
dotenvx run -- uv run pyright
dotenvx run -- uv run pytest tests/auth tests/app tests/tools tests/web tests/observability -q
dotenvx run -- uv run pytest tests/conversations tests/database -q
```

Expected: ruff and pyright report no errors; all tests pass.

- [ ] **Step 3: Verify live behavior and commit**

Confirm the frontend status flow and all four metrics at `/metrics`.

Commit: `git add README.md backend/README.md && git commit -m "docs: explain tool progress and availability"`

## Plan Self-Review

- Tasks 1–3 implement tool-owned user progress without central name maps.
- Task 4 closes both failed issue conditions.
- Task 5 validates the complete issue contract.
