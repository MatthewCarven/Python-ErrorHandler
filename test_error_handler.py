"""
Unit tests for error_handler.describe_error.

Run with:
    python -m unittest test_error_handler.py

These tests pin down the function's CONTRACT, not implementation details.
Each test exercises one promise: never raises, dict shape stable, safety net
catches broken __repr__/__str__, chain walking honors guards, dispatch table
finds the right extractor via MRO, flags toggle behavior as documented.

For visual examples of actual output, see test_chain.py / test_dispatch.py /
test_locals.py / test_formatter.py / test_heavy.py / test_caller_context.py
/ test_group.py - those are runnable documentation rather than assertion
tests.
"""

import sys
import unittest

from error_handler import describe_error, ErrorReport


# ---------------------------------------------------------------------------
# Adversarial classes used across multiple tests
# ---------------------------------------------------------------------------

class BrokenStr(Exception):
    """Exception where str() raises - exercises the message-step safety net."""
    def __str__(self):
        raise RuntimeError("str() is broken")


class BrokenRepr:
    """Non-exception class with a broken __repr__. Used to test that locals
    capture survives values with hostile reprs without breaking the rest."""
    def __repr__(self):
        raise RuntimeError("repr is broken")


class HostileNonException:
    """Not a BaseException subclass. describe_error should still produce a
    usable report when handed one of these instead of crashing."""
    pass


# ---------------------------------------------------------------------------
# Happy path - the basic contract
# ---------------------------------------------------------------------------

class HappyPathTests(unittest.TestCase):

    def test_returns_error_report_instance(self):
        try:
            int("nope")
        except Exception as e:
            report = describe_error(e)
        self.assertIsInstance(report, ErrorReport)
        self.assertIsInstance(report.to_dict(), dict)
        self.assertIsInstance(report.to_string(), str)
        self.assertIsInstance(report.for_claude(), str)
        # __str__ should delegate to to_string().
        self.assertEqual(str(report), report.to_string())

    def test_dict_shape_contains_expected_keys(self):
        try:
            int("nope")
        except Exception as e:
            d = describe_error(e).to_dict()
        for key in (
            "type", "module", "message", "repr", "args", "notes",
            "extra_attrs", "type_specific", "traceback", "chain",
            "partial_failures",
        ):
            self.assertIn(key, d, "missing key: " + key)

    def test_basic_fields_populated(self):
        try:
            int("not a number")
        except Exception as e:
            d = describe_error(e).to_dict()
        self.assertEqual(d["type"], "ValueError")
        self.assertEqual(d["module"], "builtins")
        self.assertIn("not a number", d["message"])
        self.assertIn("ValueError", d["repr"])
        self.assertEqual(d["partial_failures"], [])

    def test_traceback_frames_captured(self):
        def inner():
            raise RuntimeError("kaboom")
        try:
            inner()
        except Exception as e:
            d = describe_error(e).to_dict()
        # At least the inner() frame and its caller.
        self.assertGreaterEqual(len(d["traceback"]), 2)
        func_names = [f["function"] for f in d["traceback"]]
        self.assertIn("inner", func_names)
        for f in d["traceback"]:
            self.assertIn("file", f)
            self.assertIn("line", f)
            self.assertIn("function", f)
            self.assertIn("code", f)


# ---------------------------------------------------------------------------
# Bare call (sys.exc_info fallback)
# ---------------------------------------------------------------------------

class BareCallTests(unittest.TestCase):

    def test_bare_call_with_active_exception(self):
        try:
            int("nope")
        except Exception:
            d = describe_error().to_dict()
        self.assertEqual(d["type"], "ValueError")

    def test_bare_call_with_no_active_exception_returns_marker(self):
        d = describe_error().to_dict()
        self.assertTrue(d.get("no_active_exception"))
        self.assertFalse(d.get("error_handler_failed"))


# ---------------------------------------------------------------------------
# Safety net - the heart of the design
# ---------------------------------------------------------------------------

class SafetyNetTests(unittest.TestCase):

    def test_broken_str_records_partial_failure(self):
        try:
            raise BrokenStr("real message in args")
        except Exception as e:
            d = describe_error(e).to_dict()
        # message() failed -> fallback string
        self.assertEqual(d["message"], "<unrenderable>")
        # repr() still works (only __str__ is broken)
        self.assertIn("BrokenStr", d["repr"])
        # partial_failures should include a 'message' step entry
        steps = [f["step"] for f in d["partial_failures"]]
        self.assertIn("message", steps)

    def test_broken_repr_in_locals_uses_fallback(self):
        def trigger():
            bomb = BrokenRepr()
            benign = "still ok"
            raise RuntimeError("boom")
        try:
            trigger()
        except Exception as e:
            d = describe_error(e, include_locals=True).to_dict()
        # Find the trigger() frame.
        target = next(f for f in d["traceback"] if f["function"] == "trigger")
        locs = target["locals"]
        self.assertIn("bomb", locs)
        self.assertIn("benign", locs)
        # Benign value comes through cleanly; bomb gets the fallback string.
        self.assertEqual(locs["benign"], "'still ok'")
        self.assertIn("<unrepresentable", locs["bomb"])

    def test_hostile_nonexception_object_doesnt_crash(self):
        # Pass an instance of a class that isn't a BaseException subclass.
        # describe_error should NOT raise; it should still produce a usable report.
        report = describe_error(HostileNonException())
        d = report.to_dict()
        self.assertEqual(d["type"], "HostileNonException")
        # And to_string should also work without crashing.
        self.assertIsInstance(report.to_string(), str)


# ---------------------------------------------------------------------------
# Chain walking
# ---------------------------------------------------------------------------

class ChainTests(unittest.TestCase):

    def test_explicit_cause_chain(self):
        try:
            try:
                {}["missing"]
            except KeyError as e:
                raise ValueError("wrapped") from e
        except Exception as e:
            d = describe_error(e).to_dict()
        self.assertEqual(len(d["chain"]), 1)
        self.assertEqual(d["chain"][0]["relation"], "cause")
        self.assertEqual(d["chain"][0]["type"], "KeyError")

    def test_implicit_context_chain(self):
        try:
            try:
                {}["missing"]
            except KeyError:
                raise ValueError("wrapped")
        except Exception as e:
            d = describe_error(e).to_dict()
        self.assertEqual(len(d["chain"]), 1)
        self.assertEqual(d["chain"][0]["relation"], "context")
        self.assertEqual(d["chain"][0]["type"], "KeyError")

    def test_no_chain_when_unchained(self):
        try:
            int("nope")
        except Exception as e:
            d = describe_error(e).to_dict()
        self.assertEqual(d["chain"], [])

    def test_cycle_detected_in_chain(self):
        try:
            a = RuntimeError("a")
            b = RuntimeError("b")
            a.__cause__ = b
            b.__cause__ = a
            raise a
        except Exception as e:
            d = describe_error(e).to_dict()
        markers = [c for c in d["chain"] if c.get("truncated") == "cycle_detected"]
        self.assertEqual(len(markers), 1)

    def test_max_chain_depth_respected(self):
        try:
            head = RuntimeError("head")
            cur = head
            for i in range(20):
                nxt = RuntimeError("link-" + str(i))
                cur.__cause__ = nxt
                cur = nxt
            raise head
        except Exception as e:
            d = describe_error(e, max_chain_depth=5).to_dict()
        real_links = [c for c in d["chain"] if not c.get("truncated")]
        self.assertEqual(len(real_links), 5)
        truncs = [c for c in d["chain"] if c.get("truncated") == "max_depth_reached"]
        self.assertEqual(len(truncs), 1)


# ---------------------------------------------------------------------------
# Type-specific dispatch
# ---------------------------------------------------------------------------

class DispatchTests(unittest.TestCase):

    def test_keyerror_type_specific_extractor(self):
        try:
            {"a": 1}["missing"]
        except Exception as e:
            d = describe_error(e).to_dict()
        self.assertIn("missing_key", d["type_specific"])
        self.assertIn("missing", d["type_specific"]["missing_key"])

    def test_oserror_type_specific_extractor(self):
        try:
            open("/definitely/not/a/real/path/anywhere.txt")
        except OSError as e:
            d = describe_error(e).to_dict()
        ts = d["type_specific"]
        self.assertIn("errno", ts)
        self.assertIn("strerror", ts)
        self.assertIn("filename", ts)

    def test_filenotfounderror_inherits_via_mro(self):
        # FileNotFoundError isn't directly registered; should walk MRO and
        # land on the OSError extractor.
        try:
            open("/nope/nope/nope.txt")
        except FileNotFoundError as e:
            d = describe_error(e).to_dict()
        self.assertEqual(d["type"], "FileNotFoundError")
        # Confirm OSError-shaped fields came through (proves MRO walking).
        self.assertIn("errno", d["type_specific"])

    def test_unregistered_type_returns_empty_dict(self):
        try:
            int("nope")
        except ValueError as e:
            d = describe_error(e).to_dict()
        self.assertEqual(d["type_specific"], {})


# ---------------------------------------------------------------------------
# include_locals flag
# ---------------------------------------------------------------------------

class LocalsFlagTests(unittest.TestCase):

    def test_include_locals_default_off(self):
        try:
            x = "secret"
            int("nope")
        except Exception as e:
            d = describe_error(e).to_dict()
        for f in d["traceback"]:
            self.assertNotIn("locals", f)

    def test_include_locals_captures_frame_locals(self):
        def fn_with_locals():
            magic_number = 42
            magic_string = "abracadabra"
            int("nope")
        try:
            fn_with_locals()
        except Exception as e:
            d = describe_error(e, include_locals=True).to_dict()
        target = next(
            f for f in d["traceback"] if f["function"] == "fn_with_locals"
        )
        self.assertIn("locals", target)
        self.assertEqual(target["locals"]["magic_number"], "42")
        self.assertEqual(target["locals"]["magic_string"], "'abracadabra'")


# ---------------------------------------------------------------------------
# Source context window (new)
# ---------------------------------------------------------------------------

class SourceContextTests(unittest.TestCase):

    def test_source_context_captured_by_default(self):
        try:
            int("nope")
        except Exception as e:
            d = describe_error(e).to_dict()
        for f in d["traceback"]:
            self.assertIn("source_context", f)
            self.assertIsInstance(f["source_context"], list)

    def test_source_context_marks_error_line(self):
        def boom():
            raise RuntimeError("kaboom")
        try:
            boom()
        except Exception as e:
            d = describe_error(e).to_dict()
        target = next(f for f in d["traceback"] if f["function"] == "boom")
        ctx = target["source_context"]
        # Exactly one line should be the error line.
        marked = [c for c in ctx if c["is_error_line"]]
        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0]["lineno"], target["line"])

    def test_source_context_is_dedented(self):
        # Function body is indented; the captured window should have the
        # common leading whitespace stripped so it reads cleanly.
        def deeply():
            def nested():
                raise RuntimeError("kaboom")
            nested()
        try:
            deeply()
        except Exception as e:
            d = describe_error(e).to_dict()
        target = next(f for f in d["traceback"] if f["function"] == "nested")
        ctx = target["source_context"]
        # At least one non-blank line should start with non-whitespace after
        # dedent (otherwise dedent didn't run).
        non_blank = [c["text"] for c in ctx if c["text"].strip()]
        self.assertTrue(non_blank, "expected captured non-blank lines")
        self.assertTrue(
            any(not line.startswith(" ") for line in non_blank),
            "expected at least one line to be flush left after dedent",
        )

    def test_source_context_disabled_when_zero(self):
        try:
            int("nope")
        except Exception as e:
            d = describe_error(e, source_context_lines=0).to_dict()
        for f in d["traceback"]:
            self.assertNotIn("source_context", f)


# ---------------------------------------------------------------------------
# Caller context (new)
# ---------------------------------------------------------------------------

class CallerContextTests(unittest.TestCase):

    def test_caller_context_captured_by_default(self):
        def thrower():
            raise RuntimeError("kaboom")
        try:
            thrower()
        except Exception as e:
            d = describe_error(e).to_dict()
        self.assertIn("caller_context", d)
        # Test method is itself a caller above the catch -> non-empty list.
        self.assertGreater(len(d["caller_context"]), 0)

    def test_caller_context_skips_error_handler_frames(self):
        import os
        import error_handler as eh_module
        eh_file = os.path.normcase(os.path.abspath(eh_module.__file__))
        try:
            int("nope")
        except Exception as e:
            d = describe_error(e).to_dict()
        # No captured caller frame should be exactly the error_handler module
        # file. (Substring matching is wrong here because the test file path
        # CONTAINS 'error_handler.py' as a substring.)
        for f in d["caller_context"]:
            if f.get("truncated"):
                continue
            cap_file = os.path.normcase(os.path.abspath(f["file"]))
            self.assertNotEqual(
                cap_file, eh_file,
                "caller_context leaked an internal frame: " + str(f),
            )

    def test_caller_context_disabled_when_flag_false(self):
        try:
            int("nope")
        except Exception as e:
            d = describe_error(e, caller_context=False).to_dict()
        self.assertNotIn("caller_context", d)

    def test_caller_context_respects_max_frames(self):
        # Recurse deeper than the cap so we know more frames exist.
        def recurse(n):
            if n <= 0:
                try:
                    int("nope")
                except Exception as e:
                    return describe_error(e, max_caller_frames=3).to_dict()
            return recurse(n - 1)
        d = recurse(10)
        real = [f for f in d["caller_context"] if not f.get("truncated")]
        self.assertEqual(len(real), 3)
        truncs = [
            f for f in d["caller_context"]
            if f.get("truncated") == "max_caller_frames_reached"
        ]
        self.assertEqual(len(truncs), 1)

    def test_caller_context_honors_include_locals(self):
        def helper():
            sentinel_name = "sentinel_value"
            try:
                int("nope")
            except Exception as e:
                return describe_error(e, include_locals=True).to_dict()
        d = helper()
        # Find the helper frame in caller_context (it's the immediate frame
        # above the catch since the catch IS in helper).
        # Actually the catch is in helper, so caller_context[0] is the test
        # method that called helper. The helper frame is inside traceback,
        # not caller_context. Check that caller_context frames carry locals
        # when the flag is on.
        for f in d["caller_context"]:
            if f.get("truncated"):
                continue
            self.assertIn("locals", f)


# ---------------------------------------------------------------------------
# ExceptionGroup support (new) - Python 3.11+
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    sys.version_info >= (3, 11),
    "ExceptionGroup requires Python 3.11+ (or `exceptiongroup` backport)",
)
class GroupTests(unittest.TestCase):

    def _make_group(self):
        children = []
        try:
            raise TypeError("type-child")
        except TypeError as e:
            children.append(e)
        try:
            raise ValueError("value-child")
        except ValueError as e:
            children.append(e)
        return ExceptionGroup("outer", children)

    def test_group_children_field_present_for_group(self):
        try:
            raise self._make_group()
        except BaseException as e:
            d = describe_error(e).to_dict()
        self.assertIn("group_children", d)
        self.assertEqual(len(d["group_children"]), 2)

    def test_group_children_field_absent_for_non_group(self):
        try:
            int("nope")
        except Exception as e:
            d = describe_error(e).to_dict()
        self.assertNotIn("group_children", d)

    def test_group_children_have_full_introspection(self):
        try:
            raise self._make_group()
        except BaseException as e:
            d = describe_error(e).to_dict()
        types = [c["type"] for c in d["group_children"]]
        self.assertIn("TypeError", types)
        self.assertIn("ValueError", types)
        # Each child has its own traceback.
        for child in d["group_children"]:
            self.assertIn("traceback", child)
            self.assertGreater(len(child["traceback"]), 0)

    def test_nested_groups_recurse(self):
        inner_children = []
        try:
            raise KeyError("inner-key")
        except KeyError as e:
            inner_children.append(e)
        inner = ExceptionGroup("inner", inner_children)
        outer = ExceptionGroup("outer", [inner])
        try:
            raise outer
        except BaseException as e:
            d = describe_error(e).to_dict()
        self.assertEqual(len(d["group_children"]), 1)
        inner_data = d["group_children"][0]
        self.assertIn("group_children", inner_data)
        self.assertEqual(inner_data["group_children"][0]["type"], "KeyError")

    def test_type_specific_extractors_fire_on_group_children(self):
        # KeyError's missing_key extractor should still trigger when the
        # KeyError is buried inside a group.
        children = []
        try:
            {}["missing"]
        except KeyError as e:
            children.append(e)
        group = ExceptionGroup("g", children)
        try:
            raise group
        except BaseException as e:
            d = describe_error(e).to_dict()
        child = d["group_children"][0]
        self.assertIn("missing_key", child["type_specific"])
        self.assertIn("missing", child["type_specific"]["missing_key"])

    def test_max_group_depth_caps_nesting(self):
        # Build a 5-deep group nest, ask for depth 2 -> truncation marker.
        inner = ExceptionGroup("d5", [RuntimeError("leaf")])
        for i in range(4, 0, -1):
            inner = ExceptionGroup("d" + str(i), [inner])
        try:
            raise inner
        except BaseException as e:
            d = describe_error(e, max_group_depth=2).to_dict()
        # Drill down until we hit the truncation marker.
        node = d
        depth = 0
        while "group_children" in node and node["group_children"]:
            child = node["group_children"][0]
            if child.get("truncated") == "max_group_depth_reached":
                break
            node = child
            depth += 1
            if depth > 10:
                self.fail("never hit max_group_depth truncation marker")
        else:
            self.fail("never reached a truncation marker")


if __name__ == "__main__":
    unittest.main(verbosity=2)
