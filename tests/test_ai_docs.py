"""AI integration documentation regression checks."""

from pathlib import Path


def test_ai_integration_docs_distinguish_windows_wrapper_from_linux_api():
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    client_readme = (root / "tools" / "cove-api" / "README.md").read_text(
        encoding="utf-8"
    )
    wrapper_rules = (
        root / "tools" / "cove-api" / "AI_WRAPPER_OPERATING_RULES.md"
    ).read_text(encoding="utf-8")
    direct_rules = (
        root / "tools" / "cove-api" / "AI_DIRECT_API_OPERATING_RULES.md"
    ).read_text(encoding="utf-8")

    assert "Windows-only companion" in readme
    assert "recommended on Linux" in readme
    assert "The packaged wrapper is Windows-specific" in client_readme
    assert "Running `cove_api.py` directly on Linux is not a supported" in client_readme
    assert "Windows-only instructions" in wrapper_rules
    assert "cross-platform instructions" in direct_rules
    assert "integration method on Linux" in direct_rules
