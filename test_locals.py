"""Quick verification for Task 6 - include_locals flag."""
from error_handler import describe_error


# 1) Default behavior (locals NOT captured)
print("=== 1) include_locals=False (default) ===")

def do_thing(secret_password, important_number):
    intermediate = secret_password + "!"
    return int(intermediate)

try:
    do_thing("hunter2", 42)
except Exception as e:
    r = describe_error(e).to_dict()
    print("frames captured:", len(r["traceback"]))
    for i, f in enumerate(r["traceback"]):
        has_locals = "locals" in f
        print(f"  frame {i}: function={f['function']}, has_locals={has_locals}")
    print("partial_failures:", r["partial_failures"])

# 2) include_locals=True
print()
print("=== 2) include_locals=True ===")
try:
    do_thing("hunter2", 42)
except Exception as e:
    r = describe_error(e, include_locals=True).to_dict()
    print("frames captured:", len(r["traceback"]))
    for i, f in enumerate(r["traceback"]):
        print(f"  frame {i}: function={f['function']}")
        for k, v in (f.get("locals") or {}).items():
            print(f"    {k} = {v}")
    print("partial_failures:", r["partial_failures"])

# 3) Locals on chain links too
print()
print("=== 3) include_locals=True applies to chain links ===")
def inner_with_secret(s):
    return int(s)

def outer_wrapper():
    try:
        inner_with_secret("nope")
    except Exception as e:
        raise RuntimeError("re-raised") from e

try:
    outer_wrapper()
except Exception as e:
    r = describe_error(e, include_locals=True).to_dict()
    print("primary frames:")
    for i, f in enumerate(r["traceback"]):
        loc_keys = list((f.get("locals") or {}).keys())
        print(f"  frame {i}: {f['function']} - local keys: {loc_keys}")
    print("chain[0] frames:")
    for i, f in enumerate(r["chain"][0]["traceback"]):
        loc_keys = list((f.get("locals") or {}).keys())
        print(f"  frame {i}: {f['function']} - local keys: {loc_keys}")

# 4) Adversarial: a local with a broken __repr__ shouldn't crash capture
print()
print("=== 4) adversarial: local with broken __repr__ ===")
class Nasty:
    def __repr__(self):
        raise RuntimeError("repr broken")

def has_nasty_local():
    bomb = Nasty()
    benign = "I am fine"
    return int("not a number")

try:
    has_nasty_local()
except Exception as e:
    r = describe_error(e, include_locals=True).to_dict()
    bad_frame = None
    for f in r["traceback"]:
        if f["function"] == "has_nasty_local":
            bad_frame = f
            break
    print("Locals from the bad frame:")
    for k, v in (bad_frame.get("locals") or {}).items():
        print(f"  {k} = {v}")
    print("partial_failures count:", len(r["partial_failures"]))

# 5) Confirm default truly defaults off (sanity)
print()
print("=== 5) explicit include_locals=False - locals absent ===")
try:
    do_thing("hunter2", 42)
except Exception as e:
    r = describe_error(e, include_locals=False).to_dict()
    any_locals = any("locals" in f for f in r["traceback"])
    print("any frame has locals key:", any_locals, "(expect False)")
