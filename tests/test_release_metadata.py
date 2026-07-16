"""Release-version consistency checks."""

from pathlib import Path

from cove import __version__


def test_release_metadata_uses_package_version():
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert f'version = "{__version__}"' in pyproject
    assert f"release-v{__version__}-" in readme
    assert f"## {__version__} -" in changelog
    assert "## What's new in VERSION" in workflow
