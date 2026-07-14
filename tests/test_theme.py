from cove import theme


def test_dialog_background_rule_declared_after_generic_widget_rule():
    """Qt's stylesheet cascade resolves equal-specificity type-selector ties
    by "last rule wins". QDialog/QMainWindow is-a QWidget, so their
    background-color rule must be textually declared after the generic
    `QWidget { background-color: transparent; }` rule, or dialogs render
    with a transparent (native-fallback) background instead of the theme's
    BG color - invisible in dark mode by coincidence, but breaks light mode
    outright (see the light-mode Settings dialog readability bug)."""
    qss = theme._build_qss()
    generic_widget_idx = qss.index("QWidget {")
    dialog_bg_idx = qss.index("QMainWindow, QDialog, QWidget#chrome {")
    assert dialog_bg_idx > generic_widget_idx


def test_qss_builds_for_both_themes():
    for name in ("dark", "light"):
        qss = theme.set_theme(name)
        assert theme.BG in qss
        assert theme.TEXT in qss
    theme.set_theme("dark")


def test_double_spin_boxes_receive_complete_input_styling():
    qss = theme._build_qss()
    assert "QSpinBox, QDoubleSpinBox," in qss
    assert "QSpinBox:focus, QDoubleSpinBox:focus" in qss
    assert "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button" in qss
