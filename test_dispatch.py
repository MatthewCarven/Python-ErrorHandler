"""Quick verification for Task 5 - type-specific dispatch table."""
from error_handler import describe_error


def show(label, e):
    r = describe_error(e).to_dict()
    print(f"=== {label} ===")
    print(f"  type: {r['type']}")
    print(f"  type_specific: {r['type_specific']}")
    print(f"  partial_failures: {r['partial_failures']}")
    print()


# 1) OSError - errno, strerror, filename
print("# 1) OSError")
try:
    open("/this/path/does/not/exist/anywhere.txt")
except OSError as e:
    show("OSError (FileNotFoundError) - inherits via MRO", e)

# 2) SyntaxError - lineno, offset, text
print("# 2) SyntaxError")
try:
    compile("def foo(:\n", "<string>", "exec")
except SyntaxError as e:
    show("SyntaxError", e)

# 3) AttributeError - name + obj (Python 3.10+)
print("# 3) AttributeError")
class Foo:
    pass
try:
    Foo().bar
except AttributeError as e:
    show("AttributeError", e)

# 4) KeyError - missing_key
print("# 4) KeyError")
try:
    {"a": 1}["missing"]
except KeyError as e:
    show("KeyError", e)

# 5) UnicodeError - encoding/start/end/reason
print("# 5) UnicodeError (via UnicodeDecodeError - inherits)")
try:
    b"\xff\xfe".decode("utf-8")
except UnicodeError as e:
    show("UnicodeDecodeError - inherits via MRO", e)

# 6) Subclass via MRO - FileNotFoundError uses OSError extractor
print("# 6) FileNotFoundError - confirms MRO walking")
try:
    open("/nope/nope/nope.txt")
except FileNotFoundError as e:
    show("FileNotFoundError - should use OSError extractor", e)

# 7) Unregistered type - should produce empty type_specific dict
print("# 7) Vanilla ValueError - no registered extractor")
try:
    int("not a number")
except ValueError as e:
    show("ValueError - type_specific should be {}", e)

# 8) Chain link gets its OWN type_specific too
print("# 8) Type-specific on chained exception")
try:
    try:
        {"a": 1}["missing"]
    except KeyError as e:
        raise ValueError("wrapped") from e
except Exception as e:
    r = describe_error(e).to_dict()
    print(f"=== primary {r['type']} ===")
    print(f"  type_specific: {r['type_specific']}")
    print(f"  chain[0] type: {r['chain'][0]['type']}")
    print(f"  chain[0] type_specific: {r['chain'][0]['type_specific']}")
