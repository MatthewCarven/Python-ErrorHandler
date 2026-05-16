# Python ErrorHandler - Quickstart

## What it is

One function - `describe_error(exc)` - that lives inside an `except` clause and returns an `ErrorReport` containing everything knowable about the exception. **Never raises.**

## Drop-in usage

```python
import sys
from error_handler import describe_error

def main():
    ...  # your program

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(describe_error(e), file=sys.stderr)
        sys.exit(1)
```

That gets you a Python-style traceback with type-specific fields, notes, and the full cause/context chain - automatically.

## Three output flavors

```python
report = describe_error(e)

print(report)                      # concise traceback-style (also via __str__)
print(report.for_claude())         # verbose / labeled / LLM-friendly
metrics.send(report.to_dict())     # structured, JSON-able
```

## When you need locals

For deep debugging, pass `include_locals=True`. **OFF by default** because frame locals can contain secrets (passwords, tokens, etc.).

```python
print(describe_error(e, include_locals=True).for_claude())
```

## Bare call inside except

`describe_error()` with no argument falls back to `sys.exc_info()`, so this works too:

```python
try:
    risky()
except Exception:
    log.error(describe_error())   # no arg needed
```

## What you get for free

- Exception type, module, message, repr, args, `__notes__`
- Full traceback with source context window (3 lines either side of the error line, dedented)
- Caller context — the frames ABOVE the catch site, so you also see who called the handler
- `ExceptionGroup` walked recursively (Python 3.11+ or the 3.10 `exceptiongroup` backport)
- Cause and context chain (cycle-safe, depth-capped)
- Type-specific fields for common builtins (`OSError`, `KeyError`, `SyntaxError`, `AttributeError`, `UnicodeError`)
- Environment snapshot (Python version, platform, cwd, pid, argv) for portable crash reports
- Partial-failure tracking if introspection itself hit a snag

## Redacting secrets

If `include_locals=True` might surface tokens, passwords, or API keys, register a redactor:

```python
from error_handler import register_redactor, redact_pattern

register_redactor(redact_pattern(r"sk-[A-Za-z0-9]{20,}"))
register_redactor(redact_pattern(r"password=\S+", "password=<redacted>"))
```

Redactors run on every captured string (locals, source lines, messages, notes). See `GUIDE.md` for the full hook surface.

## That's it

For type-specific extractor registration, full output dict schema, integration patterns, and safety guarantees, see `GUIDE.md`.
