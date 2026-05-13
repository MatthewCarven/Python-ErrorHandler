"""Visual test for Task 9 - heavy / for_claude() formatter."""
from error_handler import describe_error


def banner(label):
    print()
    print("#" * 70)
    print("# " + label)
    print("#" * 70)


# 1) Simple exception - exercises all the labeled sections
banner("1) Plain ValueError - all sections labeled")
try:
    int("not a number")
except Exception as e:
    print(describe_error(e).for_claude())


# 2) Chained exception with locals - the full demonstration
banner("2) Chained exception (cause) with include_locals=True")

def parse_user(blob):
    user_age = blob["age"]
    return int(user_age)

def handle(blob):
    try:
        return parse_user(blob)
    except KeyError as e:
        operation = "user-payload-parse"
        raise ValueError("payload missing required field") from e

try:
    handle({"name": "matt"})
except Exception as e:
    print(describe_error(e, include_locals=True).for_claude())


# 3) Exception with notes + type-specific details
banner("3) KeyError with notes")
try:
    try:
        d = {"a": 1}
        d["missing"]
    except KeyError as e:
        if hasattr(e, "add_note"):
            e.add_note("Looking up config value for user 12345")
            e.add_note("Config file: /etc/myapp/config.json")
        raise
except Exception as e:
    print(describe_error(e).for_claude())


# 4) Cyclic chain - truncation marker in the chain section
banner("4) Cyclic chain - truncation in CAUSE / CONTEXT CHAIN section")
try:
    a = RuntimeError("first")
    b = RuntimeError("second")
    a.__cause__ = b
    b.__cause__ = a
    raise a
except Exception as e:
    print(describe_error(e).for_claude())


# 5) Partial failures called out
banner("5) Partial failures - INTERNAL CAPTURE ISSUES section")

class BrokenStr(Exception):
    def __str__(self):
        raise RuntimeError("str() is broken")

try:
    raise BrokenStr("real message in args")
except Exception as e:
    print(describe_error(e).for_claude())


# 6) No active exception - the alt path
banner("6) Bare describe_error() with no active exception")
print(describe_error().for_claude())
