"""Portable-mode detection and packaging regression tests."""
from pathlib import Path

from cove import portable


def test_explicit_portable_mode_works_in_a_fresh_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "_exe_dir", lambda: str(tmp_path))
    monkeypatch.setenv(portable.PORTABLE_ENV, "1")

    assert portable.is_portable() is True
    data_dir = Path(portable.portable_data_dir("cove-download-manager"))
    assert data_dir == tmp_path / "cove-app-data" / "cove-download-manager"
    assert data_dir.is_dir()


def test_clean_directory_is_not_implicitly_portable(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "_exe_dir", lambda: str(tmp_path))
    monkeypatch.delenv(portable.PORTABLE_ENV, raising=False)

    assert portable.is_portable() is False


def test_existing_marker_still_enables_portable_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "_exe_dir", lambda: str(tmp_path))
    monkeypatch.delenv(portable.PORTABLE_ENV, raising=False)
    (tmp_path / "portable.marker").touch()

    assert portable.is_portable() is True


def test_windows_builds_use_portable_bootstrap_only_for_one_file():
    root = Path(__file__).resolve().parents[1]
    native = (root / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
    wine = (root / "scripts" / "build-windows-wine.sh").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    native_portable = native.split("$PortableDist", 1)[1].split("if ($Setup)", 1)[0]
    native_installer = native.split("if ($Setup)", 1)[1]
    assert '"packaging\\portable_launcher.py"' in native_portable
    assert '"packaging\\launcher.py"' in native_installer

    wine_installer = wine.split("# ---------------------------------------------------------------- 4. one-dir", 1)[1]
    wine_installer, wine_portable = wine_installer.split(
        "# ---------------------------------------------------------------- 5. one-file", 1
    )
    assert "packaging/launcher.py" in wine_installer
    assert "packaging/portable_launcher.py" in wine_portable

    workflow_installer = workflow.split("- name: PyInstaller (one-dir for installer)", 1)[1]
    workflow_installer, workflow_portable = workflow_installer.split(
        "- name: PyInstaller (one-file portable)", 1
    )
    workflow_portable = workflow_portable.split("- name: Install Inno Setup", 1)[0]
    assert "packaging/launcher.py" in workflow_installer
    assert "packaging/portable_launcher.py" in workflow_portable


def test_portable_bootstrap_sets_mode_before_importing_cove():
    root = Path(__file__).resolve().parents[1]
    source = (root / "packaging" / "portable_launcher.py").read_text(
        encoding="utf-8"
    )

    assert source.index('os.environ["COVE_PORTABLE"] = "1"') < source.index(
        "from cove.entry import main"
    )
