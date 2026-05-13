# Python ErrorHandler — Build Tasks

Mirrored from session task list on 2026-05-13. Status updates happen here and in the in-session task tracker.

## Goal

One function — `describe_error(exc)` — that lives inside an `except` clause and surfaces a string (or dict) containing everything knowable about the immediate Python error, so the caller can do something useful with it instead of discarding it.

## Build order

1. **Scaffold `describe_error` skeleton with safety net** — `error_handler.py` with the public signature, the `_safe_capture` helper, and the outermost fallback wrapper that returns `{"error_handler_failed": True, ...}` if the handler itself crashes. No introspection yet — just the protective shell.

2. **Implement generic exception extractor** — capture the universally-available fields: type name, module, `str(e)` message, `args`, `__notes__`. Default extractor when no type-specific handler matches.

3. **Implement traceback walker (no locals)** — walk `e.__traceback__` via the `traceback` module and produce a list of frame dicts: file, line, function, code text. Each frame capture wrapped in `_safe_capture`.

4. **Implement chain walker with cycle and depth guards** — follow `__cause__` first, then `__context__` if `__suppress_context__` is False. `visited` set keyed on `id(exc)` to break cycles. Honor `max_chain_depth` as a hard stop.

5. **Build dispatch table with seed extractors** — `_register` decorator and `_TYPE_EXTRACTORS` registry. MRO-walking lookup so subclasses inherit. Seed with `OSError`, `SyntaxError`, `AttributeError`, `KeyError`, `UnicodeError`.

6. **Add locals capture behind `include_locals` flag** — capture `frame.f_locals` for each traceback frame, run each value through `_safe_repr(v, max_len=200)`. Default off for security.

7. **Write concise string formatter consuming the dict** — separate function, traceback-style multi-line output. Backs `ErrorReport.to_string()` and `__str__`. Keeps the dict builder reusable for JSON/logfmt consumers.

8. **Implement `for_claude()` heavy-edition formatter** — verbose, fully labeled, LLM-friendly output. Every section explicitly named (PRIMARY EXCEPTION / WHERE IT HAPPENED / CAUSE CHAIN / TYPE-SPECIFIC DETAILS / INTERNAL CAPTURE ISSUES). Each chain link rendered fully with its own where-it-happened block. `partial_failures` called out so an LLM reader knows what was missed.

9. **Write tests including adversarial broken-repr cases** — bare call (`sys.exc_info` fallback), chained exceptions, cyclic chain, deep chain hitting max depth, custom exception types, type-specific extractors, `include_locals` on/off, plus adversarial: exception with a `__repr__` that raises, broken `__notes__`, frame with unrepresentable locals. Verify `partial_failures` collects these without breaking the overall output.

## Public API (planned)

```python
def describe_error(
    exc: BaseException | None = None,
    *,
    include_locals: bool = False,
    max_chain_depth: int = 10,
) -> ErrorReport:
    ...

class ErrorReport:
    def to_dict(self) -> dict: ...
    def to_string(self) -> str: ...        # concise, traceback-style
    def for_claude(self) -> str: ...       # heavy / LLM-friendly edition
    def __str__(self) -> str: ...          # delegates to to_string()
```

`describe_error(e)` returns an `ErrorReport`. `__str__` produces the human form so
it slots into `log.error(describe_error(e))` naturally. Explicit access via
`.to_dict()` / `.to_string()` / `.for_claude()`.

## Output dict shape (planned)

```python
{
    "type": "ValueError",
    "module": "builtins",
    "message": "...",
    "args": (...),
    "notes": [],
    "type_specific": {...},
    "traceback": [{"file": ..., "line": ..., "function": ..., "code": ..., "locals": {...}?}],
    "chain": [{"type": ..., "message": ..., "relation": "cause"|"context", ...}],
    "partial_failures": [],
}
```

If the handler itself blows up:

```python
{
    "error_handler_failed": True,
    "fallback_repr": repr(exc),
    "fallback_type": type(exc).__name__,
    "handler_failure": repr(internal_exc),
}
```
