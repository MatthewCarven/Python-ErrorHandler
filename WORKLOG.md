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

### Notes for the next session

- **Bash mount sync flakiness.** During this session, edits made via the file tools (Windows side) weren't always immediately reflected in the Linux bash mount the sandbox uses. Matthew ended up running tests from his Windows terminal directly to verify - that path always worked. If returning to this project from a fresh session, prefer running tests on Matthew's machine, or restart the sandbox to refresh the mount.
- **Write tool truncation around 8-10KB.** Writing the full `error_handler.py` (~300 lines / ~10KB) in a single Write got cut off mid-file twice. Workaround: write the initial scaffold then grow the file via `Edit`. Same caution applies to large guide/doc files - chunk them.
- **Integration target**: planning to drop this into Network Notepad and other projects' main init loops. The intent is `try / except / print(describe_error(e)) / sys.exit(1)` as a standard pattern.
