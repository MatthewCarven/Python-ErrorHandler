"""
Unit tests for error_handler.describe_error.

Run with:
    python -m unittest test_error_handler.py

These tests pin down the function's CONTRACT, not implementation details.
Each test exercises one promise: never raises, dict shape stable, safety net
catches broken __repr__/__str__, chain walking honors guards, dispatch table
finds the right extractor via MRO, flags toggle behavior as documented.

For visual examples of actual output, see test_chain.py / test_dispatch.py /
test_locals.py / test_formatter.py / test_heavy.py - those are runnable
documentation rather than assertion tests.
"""

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


if __name__ == "__main__":
    unittest.main()
