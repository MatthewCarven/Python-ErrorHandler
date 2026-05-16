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

## v2 additions (2026-05-15)

Three features added on top of the v1 contract. All backward-compatible:
existing fields preserved, new fields added, no breaking changes to the
public signature (only new keyword-only params).

10. **Source context window** - `source_context_lines: int = 3` captures
    N lines either side of each frame's error line, dedents common leading
    whitespace, stores as `frame["source_context"]: [{lineno, text,
    is_error_line}, ...]`. Existing `code` (single line) untouched. Applies
    uniformly to traceback frames, chain-link frames, group-child frames,
    and caller-context frames. Set to 0 to disable.

11. **Caller context** - `caller_context: bool = True` adds a top-level
    `caller_context: [frame, ...]` field on the primary exception listing
    frames ABOVE the catch site (i.e. who called the function that's now
    handling the exception). Walks `sys._getframe()` upward, skips frames
    whose filename matches `error_handler.__file__`. Capped at
    `max_caller_frames: int = 32` with a truncation marker on overflow.
    Nearest-to-oldest order (the catch's caller is frame 0).

12. **ExceptionGroup support** - For exceptions where `isinstance(exc,
    BaseExceptionGroup)` (or the 3.10 duck-type fallback succeeds), each
    member of `exc.exceptions` is recursively walked as a full
    `_build_data` result and stored under `group_children: [...]`. Nested
    groups recurse. Cap via `max_group_depth: int = 10`. Cycle-protected
    by an id-keyed visited set shared across the whole recursion.

### Updated public API

```python
def describe_error(
    exc=None,
    *,
    include_locals=False,
    max_chain_depth=10,
    source_context_lines=3,    # NEW
    caller_context=True,       # NEW
    max_caller_frames=32,      # NEW
    max_group_depth=10,        # NEW
) -> ErrorReport: ...
```

### Updated dict shape (additive)

```python
{
    ...                          # all v1 keys preserved
    "traceback": [{
        ...                      # all v1 frame keys preserved
        "source_context": [      # NEW: per frame, when source_context_lines > 0
            {"lineno": int, "text": str, "is_error_line": bool},
            ...
        ],
    }],
    "caller_context": [          # NEW: top-level, primary only
        {... same shape as traceback frames ...},
        {"truncated": "max_caller_frames_reached"},  # only when capped
    ],
    "group_children": [          # NEW: present only when exc is a group
        {... full _build_data dict, may itself contain group_children ...},
        {"truncated": "cycle_detected" | "max_group_depth_reached"},
    ],
}
```

Tests extended from 20 to 35 assertions. ExceptionGroup tests are
auto-skipped on Python < 3.11 when the `exceptiongroup` backport isn't
available.

## v2.1 additions (2026-05-15, same day)

Two more features picked from a brainstorm.

13. **Environment snapshot** - `environment_snapshot: bool = True` adds a
    top-level `environment: {python_version, python_implementation, platform,
    system, machine, executable, cwd, pid, argv}` dict to the report. Env
    var capture is OPT-IN via separate `env_vars: Iterable[str] | None`
    param so `os.environ` secrets aren't accidentally slurped. Captured
    env values pass through the active redactors. Renders as an
    `ENVIRONMENT` block in the heavy formatter; concise stays clean.

14. **Redaction hooks** - global registry + ContextVar-backed active list
    of `(str -> str)` callables that scrub captured strings. Public surface:
    `register_redactor(fn)`, `clear_redactors()`, `redact_pattern(regex,
    replacement)`. Per-call override: `redactors=` param (None = registry,
    `[]` = disable). Applied at `_safe_repr` (BEFORE truncation so partial
    secrets can't leak through the cut), source lines, source_context text,
    message, repr, notes, captured env values. Each redactor call individually
    try/except'd; broken redactors fall back rather than break.

### Updated public API (final)

```python
def describe_error(
    exc=None,
    *,
    include_locals=False,
    max_chain_depth=10,
    source_context_lines=3,
    caller_context=True,
    max_caller_frames=32,
    max_group_depth=10,
    environment_snapshot=True,    # NEW
    env_vars=None,                # NEW
    redactors=None,               # NEW
) -> ErrorReport: ...

# Redaction registry helpers (module-level)
def register_redactor(fn): ...
def clear_redactors(): ...
def redact_pattern(pattern, replacement="<redacted>", flags=0): ...
```

Tests extended from 35 to 45 assertions.
