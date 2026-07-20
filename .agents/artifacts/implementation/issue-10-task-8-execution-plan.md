# Issue #10 Task 8: Guard Sensitive Values in Logs

**Goal:** Lock the no-secret logging contract with an end-to-end test over the real login and message-streaming request paths.

## Scope

- Use unique test-only values for a password and message, then obtain the real session cookie value from a successful login.
- Perform an authenticated conversation creation and message stream with a local fake agent.
- Capture stdout and assert that none of the three sensitive values occur in the raw log text.
- Do not change logging behavior unless the audit exposes a real leak.

## Acceptance criteria

- Successful login and message streaming work in the test.
- Captured stdout excludes the exact password, message content, and raw session token.
- The assertion covers raw output rather than only JSON keys, so nested fields and formatted exceptions cannot bypass it.

## Verification

```powershell
uv run pytest tests/test_observability.py -q
uv run ruff format --check tests/test_observability.py
uv run ruff check tests/test_observability.py
uv run pyright tests/test_observability.py
uv run pytest -q
```

## References

- Issue #10 logging boundary: https://github.com/chahoseong/my-ai-assistant/issues/10
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
