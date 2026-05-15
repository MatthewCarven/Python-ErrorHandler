"""Smoke test for caller_context capture.

The __main__ block in error_handler.py can't exercise caller_context properly
because the catch lives in error_handler.py itself - every frame above it is
filtered out as "internal". This file lives outside the module, so the catch
has visible callers (catcher -> middle -> outer -> <module>) above it on the
stack. caller_context should surface those.

Run from project root:
    python test_caller_context.py
"""

from error_handler import describe_error


def boom():
    return 1 / 0


def catcher():
    """The function whose `except` will call describe_error. The frames
    above this in the stack (middle, outer, <module>) are what
    caller_context captures."""
    try:
        boom()
    except Exception as e:
        return describe_error(e)


def middle():
    intermediate_local = "I should appear if include_locals were on"
    return catcher()


def outer():
    return middle()


if __name__ == "__main__":
    report = outer()
    print("=" * 60)
    print("Concise (to_string):")
    print("=" * 60)
    print(report)
    print()
    print("=" * 60)
    print("Heavy (for_claude):")
    print("=" * 60)
    print(report.for_claude())
