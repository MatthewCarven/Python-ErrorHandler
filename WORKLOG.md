# Python ErrorHandler - Worklog

## 2026-05-13 - Initial build complete

Built `error_handler.py` from scratch with one public function `describe_error()` that surfaces everything knowable about an exception. Design contract: never raises.

### What got built (in order)

1. **Skeleton + outermost safety net** - `describe_error()` signature, `_safe_capture()` chokepoint helper, `ErrorReport` dataclass with three output flavors, outermost try/except returning `error_handler_failed` dict if everything else fails.
2. **Generic exception extractor** - type, module, message, repr, args, `__notes__`, non-dunder `vars()` attributes.
3. **Traceback walker** - walks `exc.__traceback__` linked list oldest-first, capturing file/line/function/code via `linecache`.
4. **Chain walker with cycle and depth guards** - follows `__cause__` first then `__context__` (unless suppressed), `id()`-keyed visited set for cycle detection, `max_chain_depth` hard cap, truncation markers preserved.
5. **Dispatch table** - `_register` decorator + `_TYPE_EXTRACTORS` registry. Seeded with OSError, SyntaxError, AttributeError, KeyError, UnicodeError. MRO-walked so subclasses inherit (FileNotFoundError uses OSError extractor for free).
6. **`include_locals` flag** - off by default for security; when on, captures `frame.f_locals` with each value passed through `_safe_repr` (truncating, repr-safe).
7. **Concise formatter** - Python-style chained-exception printing (oldest first, relation phrases between, primary last), with type-specific block, notes, optional locals, partial-failures section.
8. **20 unittest assertions** - happy path / bare call / safety net / chain walking / dispatch / locals flag. All passing in 5ms.
9. **`for_claude()` heavy formatter** - fully labeled, section-by-section (PRIMARY EXCEPTION / CAUSE / CONTEXT CHAIN / INTERNAL CAPTURE ISSUES). Nearest-to-oldest chain ordering rather than chronological - structured-data view for LLM consumption.

### Files in project folder

- `error_handler.py` - the module
- `test_error_handler.py` - 20 unittest assertions covering the contract
- `test_chain.py`, `test_dispatch.py`, `test_locals.py`, `test_formatter.py`, `test_heavy.py` - runnable visual examples / smoke scripts
- `TASKS.md` - the build plan we worked from
- `QUICKSTART.md` - minimal drop-in usage doc
- `GUIDE.md` - full reference doc
- `WORKLOG.md` - this file

### Key design decisions worth remembering

- **Single file, stdlib only.** No external deps, drop-in for any project. The module wants to be portable.
- **`ErrorReport` is a wrapper, not just a dict.** Three method-style accessors (`to_dict()`, `to_string()`, `for_claude()`) plus `__str__` delegating to `to_string()` so it slots into `log.error(report)` and f-strings naturally.
- **Per-step safety wrappers route everything through `_safe_capture()`.** A broken `__repr__` in the exception, in a chain link, or in a captured local should never propagate out. Failed steps land in `partial_failures` with the step name and the inner error.
- **Two truncation paths for the chain**: `cycle_detected` and `max_depth_reached`. Both are inserted as dict entries in the chain itself rather than lost silently.
- **Chain ordering differs between formatters by design.** Concise = chronological (matches Python's traceback printing). Heavy = nearest-to-oldest (matches walker order, easier for an LLM to navigate as data).
- **Dispatch table is MRO-walked.** Registering for a base type covers all subclasses. The whole table is ~5 seeded entries; projects can add their own via `_register`.

## 2026-05-15 - Source context, caller context, ExceptionGroup

Three additions to `error_handler.py`, each behind a public parameter:

### New parameters on `describe_error()`

- `source_context_lines: int = 3` - capture N lines either side of the error
  line per frame, common leading whitespace stripped. Default 3 produces a
  7-line window. Set to 0 to disable. Applies to traceback frames, chain-link
  frames, group-child frames, and caller-context frames uniformly.
- `caller_context: bool = True` - walk the call stack ABOVE the catch site
  (frames not in `exc.__traceback__`), so the report shows who called the
  function that's now handling the exception. Skips frames in error_handler.py.
- `max_caller_frames: int = 32` - cap on the caller_context walk. Truncation
  marker appended when exceeded so deeply recursive callers don't lose
  information silently.
- `max_group_depth: int = 10` - cap on nested ExceptionGroup recursion.

### New data dict keys

- Per-frame: `source_context: [{lineno, text, is_error_line}, ...]` when
  `source_context_lines > 0`. Existing `code` field unchanged for backward
  compat.
- Top-level (primary exception only): `caller_context: [frame, ...]` when
  `caller_context=True`. Same frame shape as `traceback` entries, plus
  optional `{'truncated': 'max_caller_frames_reached'}` marker.
- Per-exception: `group_children: [data_dict, ...]` when the exception is
  an ExceptionGroup. Each child is a full `_build_data` result (so it has
  its own type-specific extractor results, chain, traceback, and - if it's
  itself a group - its own `group_children`). Truncation markers for
  `cycle_detected` and `max_group_depth_reached`.

### Implementation notes

- `_frame_dict(frame, lineno, ...)` extracted as a shared helper used by
  both `_walk_traceback` (passes `tb.tb_lineno`) and `_walk_caller_context`
  (passes `frame.f_lineno`). Same frame dict shape across both axes.
- `_capture_source_context()` reads `linecache.getlines()`, slices around the
  error line, computes common leading whitespace across non-blank lines, and
  dedents. Empty list when linecache returns nothing (dynamic code, REPL).
- `_walk_caller_context()` walks `sys._getframe(N)` from N=1 upward, skipping
  frames whose `f_code.co_filename == __file__`. Once past our own frames it
  captures the rest up to `max_caller_frames`. Whole walk wrapped in a
  try/except so a broken stack walk lands in `partial_failures` instead of
  killing the report.
- `_walk_group()` recurses through `exc.exceptions`. Uses `_BaseExceptionGroup
  = BaseExceptionGroup` on 3.11+, with duck-typing fallback (`tuple-valued
  .exceptions` attr + `'ExceptionGroup'` in classname) so the module works on
  3.10 with the `exceptiongroup` backport. Cycle protection via id-keyed
  `_group_visited` set shared across the whole recursion.

### Formatter updates

- Concise: source context window replaces the single `code` line under each
  `File "..."` header (line numbers right-justified, `>>` marker on the error
  line). Caller context appended after the primary exception with its own
  header. Group children rendered inline at the end of each exception's
  block, with `+---------- group child N of M ----------` separators.
- Heavy: explicit `Source context (lines A-B):` block under each frame's
  `Code:`. New top-level `CALLER CONTEXT (N frame(s) above the catch site,
  nearest-to-oldest)` section between PRIMARY EXCEPTION and CAUSE/CONTEXT
  CHAIN. Group children rendered as labeled `--- Child K of N ---` blocks
  nested under their parent exception with deeper indent.

### Tests

Extended `test_error_handler.py` from 20 to 35 unittest assertions:

- `SourceContextTests` (4): default-on, error line marker exists and matches
  frame lineno, dedent is applied, `source_context_lines=0` disables.
- `CallerContextTests` (5): default-on, internal frames skipped, can be
  disabled, `max_caller_frames` cap with truncation marker, locals captured
  when `include_locals=True`.
- `GroupTests` (6, skipped pre-3.11): `group_children` present for groups
  and absent otherwise, children get full introspection, nested groups
  recurse, type-specific extractors fire on group children (KeyError's
  `missing_key` works inside a group), `max_group_depth` caps nesting with
  truncation marker.

Two visual smoke scripts added: `test_caller_context.py` (a callable chain
catcher -> middle -> outer -> __main__) and `test_group.py` (3-sibling
group with a nested group child).

### Hiccups this session

- Bash mount sync issue is persistent across sessions. Several Edits weren't
  reflected in the Linux bash view of files until a no-op follow-up Edit was
  applied. Matthew's Windows terminal sees the canonical state - default to
  running tests there.

## 2026-05-15 (evening) - Environment snapshot + redaction hooks

Two follow-up additions on the same day as the v2 work, picked from a
brainstorm of "what would actually earn its keep".

### Environment snapshot

New params: `environment_snapshot: bool = True`, `env_vars: Iterable[str] |
None = None`. Captures Python version + implementation, platform / system /
machine, executable path, cwd, pid, argv into top-level `environment: {...}`.
Env var capture is opt-in via the `env_vars` param to avoid accidentally
slurping secrets from `os.environ`. Each captured env-var value passes
through the active redactors.

Renders in the heavy formatter as an `ENVIRONMENT` block (between the chain
section and `INTERNAL CAPTURE ISSUES`). Concise formatter intentionally
ignores it - keeps the terse traceback-style log feel.

### Redaction hooks

ContextVar-backed active redactor list + module-level `_DEFAULT_REDACTORS`
registry. Public surface: `register_redactor(fn)`, `clear_redactors()`,
`redact_pattern(regex, replacement="<redacted>", flags=0)`. New per-call
override: `redactors=` (None = use registry, `[]` = disable for this call).

Redaction is applied at every string capture site:
- `_safe_repr` (covers locals, args, extra_attrs) - BEFORE truncation so a
  long secret can't get partially exposed by the truncation cut.
- Single-line `code` field per frame.
- Every line of `source_context` text.
- `str(exc)` message and `repr(exc)`.
- Each `__notes__` string.
- Captured env var values.

Every redactor call wrapped in `try/except` - a broken redactor falls back
to the prior string value. Safety-contract intact.

ContextVar means thread-safe and async-safe; redactors set at the start of
each `describe_error` call are reset in a `finally` so there's never any
residue between calls.

### Tests

Extended `test_error_handler.py` from 35 to 45 unittest assertions:

- `EnvironmentTests` (4): default-on, can disable, env_vars not captured by
  default, env_vars captured when requested.
- `RedactionTests` (6): redactor applies to locals, message, source_context;
  per-call `redactors=[]` overrides global; broken redactor doesn't crash;
  `clear_redactors()` works.

New smoke script `test_env_redact.py` - registers two redactors (sk- API
keys and `hunter2`), triggers an exception with secrets in source AND
locals AND message, captures PATH/HOME-equivalents, prints both concise
and heavy.

### Hiccups this session

Same bash mount sync issue as previous sessions - file tool sees the
canonical state, sandbox bash lags. Couldn't sandbox-test the new code so
deferred verification to Matthew's terminal as usual.

## Notes for the next session

- **Bash mount sync flakiness.** During this session, edits made via the file tools (Windows side) weren't always immediately reflected in the Linux bash mount the sandbox uses. Matthew ended up running tests from his Windows terminal directly to verify - that path always worked. If returning to this project from a fresh session, prefer running tests on Matthew's machine, or restart the sandbox to refresh the mount.
- **Write tool truncation around 8-10KB.** Writing the full `error_handler.py` (~300 lines / ~10KB) in a single Write got cut off mid-file twice. Workaround: write the initial scaffold then grow the file via `Edit`. Same caution applies to large guide/doc files - chunk them.
- **Integration target**: planning to drop this into Network Notepad and other projects' main init loops. The intent is `try / except / print(describe_error(e)) / sys.exit(1)` as a standard pattern.
