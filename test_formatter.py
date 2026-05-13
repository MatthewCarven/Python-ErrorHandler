"""Visual test for Task 7 - concise formatter."""
from error_handler import describe_error


def banner(label):
    print()
    print("#" * 70)
    print("# " + label)
    print("#" * 70)


# 1) Simple exception with type-specific (KeyError -> missing_key)
banner("1) KeyError with type_specific + traceback")
def lookup(d, key):
    return d[key]

try:
    lookup({"a": 1, "b": 2}, "missing")
except Exception as e:
    print(describe_error(e))


# 2) Chained: KeyError -> ValueError 'from'
banner("2) Chained exception (raise ... from ...) - cause")
def parse_user(blob):
    return int(blob["age"])

def handle_request(blob):
    try:
        return parse_user(blob)
    except KeyError as e:
        raise ValueError("malformed user payload") from e

try:
    handle_request({"name": "matt"})
except Exception as e:
    print(describe_error(e))


# 3) Implicit context (no 'from')
banner("3) Implicit context (raise during handling)")
def implicit_chain():
    try:
        {"a": 1}["missing"]
    except KeyError:
        raise RuntimeError("something else went wrong")

try:
    implicit_chain()
except Exception as e:
    print(describe_error(e))


# 4) include_locals=True - locals show under each frame
banner("4) With locals captured")
def calculate(price, quantity):
    secret_discount = "INTERNAL_USE_ONLY"
    subtotal = price * quantity
    return int(secret_discount)  # boom

try:
    calculate(9.99, 3)
except Exception as e:
    print(describe_error(e, include_locals=True))


# 5) Notes attached to exception (Python 3.11+)
banner("5) Exception with __notes__")
try:
    try:
        int("nope")
    except ValueError as e:
        if hasattr(e, "add_note"):
            e.add_note("This happened while parsing user input")
            e.add_note("See ticket #12345 for context")
        raise
except Exception as e:
    print(describe_error(e))


# 6) Cycle truncation
banner("6) Cyclic chain (truncation marker)")
try:
    a = RuntimeError("first")
    b = RuntimeError("second")
    a.__cause__ = b
    b.__cause__ = a
    raise a
except Exception as e:
    print(describe_error(e))


# 7) Depth cap truncation
banner("7) Depth-cap truncation (max_chain_depth=3)")
try:
    head = RuntimeError("primary")
    cur = head
    for i in range(10):
        nxt = RuntimeError(f"link-{i}")
        cur.__cause__ = nxt
        cur = nxt
    raise head
except Exception as e:
    print(describe_error(e, max_chain_depth=3))


# 8) Partial failures section - exception with broken __str__
banner("8) Partial failures recorded")
class BrokenStr(Exception):
    def __str__(self):
        raise RuntimeError("str() is broken on this exception")

try:
    raise BrokenStr("but the message is here in args")
except Exception as e:
    print(describe_error(e))


# 9) Non-builtin module prefix
banner("9) Custom exception class - module prefix")
import collections
try:
    raise collections.OrderedDict.__class__("not a real error")  # type: ignore
except Exception as e:
    print(describe_error(e))


# 10) error_handler_failed fallback path (forced by passing a wonky 'exception')
banner("10) The everything-failed fallback path")
class Devious:
    __traceback__ = None
    def __repr__(self):
        raise RuntimeError("repr too")
    @property
    def __class__(self):
        raise RuntimeError("even type() raises")

# This won't actually trigger the outermost fallback because it's hard to make
# describe_error fail at the outermost level — but it'll show how the
# safety net handles a hostile object passed in directly.
report = describe_error(Devious())
print(report)
