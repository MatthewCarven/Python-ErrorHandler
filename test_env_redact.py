"""Smoke test for environment snapshot + redaction hooks.

Demonstrates:
  - environment block in the heavy report
  - env_vars opt-in (here capturing PATH and HOME-equivalents)
  - a registered redactor catching a secret in source AND locals AND message

Run from project root:
    python test_env_redact.py
"""

from error_handler import describe_error, register_redactor, redact_pattern


# Register two redactors globally. These run on every captured string.
register_redactor(redact_pattern(r"sk-[A-Za-z0-9]+"))
register_redactor(redact_pattern(r"hunter2"))


def thing_with_secrets():
    api_key = "sk-totallysecretkey123"  # source-level secret
    password = "hunter2"                # source-level secret
    # Use them so they aren't optimized out (also keeps linters quiet).
    payload = {"key": api_key, "pw": password}
    raise RuntimeError("login failed with hunter2 in the message too")


if __name__ == "__main__":
    try:
        thing_with_secrets()
    except Exception as e:
        report = describe_error(
            e,
            include_locals=True,
            env_vars=["PATH", "USERPROFILE", "HOME"],
        )
        print("=" * 60)
        print("Concise (to_string):")
        print("=" * 60)
        print(report)
        print()
        print("=" * 60)
        print("Heavy (for_claude) - includes ENVIRONMENT block:")
        print("=" * 60)
        print(report.for_claude())
