"""Smoke test for ExceptionGroup support.

Requires Python 3.11+ for stdlib ExceptionGroup. On 3.10 with the
`exceptiongroup` backport, the duck-typing fallback in error_handler.py
should still pick it up, but this script uses the stdlib path so 3.10
without the backport will skip cleanly.

Run from project root:
    python test_group.py
"""

import sys
from error_handler import describe_error


def fails_a():
    raise TypeError("a thing of the wrong type")


def fails_b():
    raise ValueError("a value that wasn't allowed")


def fails_c():
    raise KeyError("nope")


def nested_group():
    """A group inside a group - exercises max_group_depth recursion."""
    children = []
    try:
        fails_c()
    except KeyError as e:
        children.append(e)
    try:
        raise RuntimeError("inner runtime issue")
    except RuntimeError as e:
        children.append(e)
    return ExceptionGroup("inner group", children)


def build_outer_group():
    """Three siblings: one TypeError, one ValueError, and a nested group
    containing a KeyError and a RuntimeError."""
    children = []
    try:
        fails_a()
    except TypeError as e:
        children.append(e)
    try:
        fails_b()
    except ValueError as e:
        children.append(e)
    children.append(nested_group())
    return ExceptionGroup("outer group", children)


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        print(
            "Skipping: stdlib ExceptionGroup needs Python 3.11+ "
            "(or the `exceptiongroup` backport on 3.10)."
        )
        sys.exit(0)

    try:
        raise build_outer_group()
    except BaseException as e:
        report = describe_error(e)
        print("=" * 60)
        print("Concise (to_string):")
        print("=" * 60)
        print(report)
        print()
        print("=" * 60)
        print("Heavy (for_claude):")
        print("=" * 60)
        print(report.for_claude())
