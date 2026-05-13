"""Quick verification for Task 4 - chain walker."""
from error_handler import describe_error


print("=== 1) explicit cause (raise ... from ...) ===")
try:
    try:
        d = {"a": 1}
        d["missing"]
    except KeyError as e:
        raise ValueError("outer error") from e
except Exception as e:
    r = describe_error(e).to_dict()
    print("primary:", r["type"], "-", r["message"])
    print("chain length:", len(r["chain"]))
    for i, link in enumerate(r["chain"]):
        print(f"  link {i}: relation={link.get('relation')}, "
              f"type={link.get('type')}, msg={link.get('message')}")
    print("partial_failures:", r["partial_failures"])

print()
print("=== 2) implicit context (raise during handling, no 'from') ===")
try:
    try:
        d = {"a": 1}
        d["missing"]
    except KeyError:
        raise ValueError("outer error")
except Exception as e:
    r = describe_error(e).to_dict()
    print("primary:", r["type"], "-", r["message"])
    print("chain length:", len(r["chain"]))
    for i, link in enumerate(r["chain"]):
        print(f"  link {i}: relation={link.get('relation')}, "
              f"type={link.get('type')}")

print()
print("=== 3) artificial cycle in __cause__ ===")
try:
    a = RuntimeError("a")
    b = RuntimeError("b")
    a.__cause__ = b
    b.__cause__ = a
    raise a
except Exception as e:
    r = describe_error(e).to_dict()
    print("chain length:", len(r["chain"]))
    for i, link in enumerate(r["chain"]):
        print(f"  link {i}: {link.get('truncated') or link.get('type')}")

print()
print("=== 4) depth cap (15-link chain, max_chain_depth=5) ===")
try:
    head = RuntimeError("head")
    cur = head
    for i in range(15):
        nxt = RuntimeError(f"link-{i}")
        cur.__cause__ = nxt
        cur = nxt
    raise head
except Exception as e:
    r = describe_error(e, max_chain_depth=5).to_dict()
    print("chain length:", len(r["chain"]), "(expect 5 links + truncation = 6)")
    print("last entry:", r["chain"][-1])

print()
print("=== 5) no chain at all (plain exception) ===")
try:
    int("nope")
except Exception as e:
    r = describe_error(e).to_dict()
    print("primary:", r["type"], "-", r["message"])
    print("chain length:", len(r["chain"]), "(expect 0)")
