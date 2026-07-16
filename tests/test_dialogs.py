"""Layout regressions for Cove dialogs."""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_settings_dialog_can_shrink_vertically_and_scroll():
    # Other test modules use QCoreApplication. Qt cannot upgrade that singleton
    # to QApplication later, so exercise the real widget in an isolated process.
    script = r'''
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from cove.config import Settings
from cove.dialogs import SettingsDialog

app = QApplication([])
dialog = SettingsDialog(Settings(
    overall_speed_limit_kbps=1536,
    speed_limiter_enabled=True,
    speed_limit_unit="MB/s",
))
dialog.resize(dialog.width(), 360)
dialog.show()
app.processEvents()
initial_speed_value = dialog.speed_limit.value()
dialog.speed_limit.setValue(2.5)
dialog.speed_unit.setCurrentText("KB/s")
app.processEvents()
print(json.dumps({
    "height": dialog.height(),
    "minimum_height": dialog.minimumSizeHint().height(),
    "scroll_policy": dialog.settings_scroll.verticalScrollBarPolicy().value,
    "expected_policy": Qt.ScrollBarAsNeeded.value,
    "scroll_maximum": dialog.settings_scroll.verticalScrollBar().maximum(),
    "outer_layout_count": dialog.layout().count(),
    "scroll_in_outer_layout": dialog.layout().indexOf(dialog.settings_scroll) >= 0,
    "initial_speed_value": initial_speed_value,
    "converted_speed_value": dialog.speed_limit.value(),
    "speed_units": [dialog.speed_unit.itemText(i) for i in range(dialog.speed_unit.count())],
    "speed_enabled_text": dialog.speed_enabled.text(),
    "speed_enabled": dialog.speed_enabled.isChecked(),
}))
dialog.close()
'''
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    metrics = json.loads(result.stdout)

    assert metrics["height"] == 360
    assert metrics["minimum_height"] < 360
    assert metrics["scroll_policy"] == metrics["expected_policy"]
    assert metrics["scroll_maximum"] > 0
    # Save/Cancel lives outside the scrolling viewport and therefore stays
    # reachable even when the form is scrolled on a short display.
    assert metrics["scroll_in_outer_layout"] is True
    assert metrics["outer_layout_count"] == 4
    assert metrics["initial_speed_value"] == 1.5
    assert metrics["converted_speed_value"] == 2560
    assert metrics["speed_units"] == ["KB/s", "MB/s"]
    assert metrics["speed_enabled_text"] == "Enable speed limiter"
    assert metrics["speed_enabled"] is True
