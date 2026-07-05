"""Cove visual theme.

Two palettes: dark (default) and light. The active palette is exposed as
module-level names (BG, ACCENT, …) so existing consumers keep working;
`set_theme(name)` rebinds those names and rebuilds QSS for live switching.

Palette token vocabulary mirrors cove-image-upscaler's CSS custom properties
so the two apps share visual identity across the dark/light boundary.
"""

from __future__ import annotations

# ── Palettes ────────────────────────────────────────────────────────────

_DARK = {
    "ACCENT": "#50e6cf",
    "ACCENT_2": "#3ddc97",
    "ACCENT_SOFT": "rgba(80, 230, 207, 0.14)",
    "ACCENT_RING": "rgba(80, 230, 207, 0.35)",
    "ACCENT_INK": "#07120f",
    "REC": "#ff5f6d",
    "REC_SOFT": "rgba(255, 95, 109, 0.14)",
    "REC_RING": "rgba(255, 95, 109, 0.35)",
    "WARN": "#ffb454",
    "WARN_SOFT": "rgba(255, 180, 84, 0.10)",
    "WARN_RING": "rgba(255, 180, 84, 0.35)",
    "BG": "#0b0b10",
    "BG_GRAD_1": "#0d0d14",
    "BG_GRAD_2": "#0a0a0f",
    "SURFACE": "#13131b",
    "SURFACE_2": "#181822",
    "SURFACE_3": "#1f1f2b",
    "SURFACE_4": "#262635",
    "BORDER": "rgba(255, 255, 255, 0.06)",
    "BORDER_STRONG": "rgba(255, 255, 255, 0.10)",
    "BORDER_STRONGER": "rgba(255, 255, 255, 0.16)",
    "WINDOW_EDGE": "rgba(255, 255, 255, 0.18)",
    "TEXT": "#ececf1",
    "TEXT_DIM": "#9a9aae",
    "TEXT_FAINT": "#6b6b80",
    "ACCENT_HEX_DIM": "#1d2c2a",
    "BORDER_HEX": "#1a1a22",
    "BORDER_HEX_STRONG": "#23232d",
    # Per-state hex used in QPalette and progress chunks.
    "ROW_ALT": "#181822",
    "SCROLLBAR_HANDLE": "rgba(255,255,255,0.06)",
    "SCROLLBAR_HANDLE_HOVER": "rgba(255,255,255,0.12)",
    "ACCENT_HOVER": "#6cebd6",
    "REC_HOVER": "#ff7a86",
    "CLOSE_HOVER_BG": "#ff5f5733",
    "CLOSE_HOVER_FG": "#ff8a82",
    "OFF_PILL_BG": "rgba(255,255,255,0.04)",
    "ICON_BTN_HOVER_BG": "#1f1f2b",
    "KBD_BG": "rgba(255, 255, 255, 0.06)",
    "KBD_BORDER": "rgba(255, 255, 255, 0.10)",
}

_LIGHT = {
    "ACCENT": "#10b9a3",
    "ACCENT_2": "#0d9e8a",
    "ACCENT_SOFT": "rgba(16, 185, 163, 0.12)",
    "ACCENT_RING": "rgba(16, 185, 163, 0.45)",
    "ACCENT_INK": "#ffffff",
    "REC": "#dc2626",
    "REC_SOFT": "rgba(220, 38, 38, 0.10)",
    "REC_RING": "rgba(220, 38, 38, 0.40)",
    "WARN": "#d97706",
    "WARN_SOFT": "rgba(217, 119, 6, 0.10)",
    "WARN_RING": "rgba(217, 119, 6, 0.40)",
    "BG": "#f7f8fa",
    "BG_GRAD_1": "#ffffff",
    "BG_GRAD_2": "#f3f5f8",
    "SURFACE": "#ffffff",
    "SURFACE_2": "#f5f7fa",
    "SURFACE_3": "#eaeef4",
    "SURFACE_4": "#dce2e9",
    "BORDER": "rgba(0, 0, 0, 0.06)",
    "BORDER_STRONG": "rgba(0, 0, 0, 0.10)",
    "BORDER_STRONGER": "rgba(0, 0, 0, 0.18)",
    "WINDOW_EDGE": "rgba(0, 0, 0, 0.28)",
    "TEXT": "#11181c",
    "TEXT_DIM": "#5b646e",
    "TEXT_FAINT": "#828e9c",
    "ACCENT_HEX_DIM": "#cfeae5",
    "BORDER_HEX": "#e1e5eb",
    "BORDER_HEX_STRONG": "#c5cfdb",
    "ROW_ALT": "#f5f7fa",
    "SCROLLBAR_HANDLE": "rgba(0,0,0,0.10)",
    "SCROLLBAR_HANDLE_HOVER": "rgba(0,0,0,0.20)",
    "ACCENT_HOVER": "#0d9e8a",
    "REC_HOVER": "#b91c1c",
    "CLOSE_HOVER_BG": "#fee2e2",
    "CLOSE_HOVER_FG": "#dc2626",
    "OFF_PILL_BG": "rgba(0,0,0,0.04)",
    "ICON_BTN_HOVER_BG": "#eaeef4",
    "KBD_BG": "rgba(0, 0, 0, 0.04)",
    "KBD_BORDER": "rgba(0, 0, 0, 0.08)",
}

# Active palette name and palette dict.
THEME = "dark"


def _apply(palette: dict) -> None:
    """Bind palette entries to module-level names so `from theme import X`
    style imports keep working. Note: callers that captured a name at
    import time will hold the OLD value — those sites read `theme.X`
    lazily instead (see widgets.Footer, app._apply_palette)."""
    g = globals()
    for k, v in palette.items():
        g[k] = v


def _palette_for(name: str) -> dict:
    return _LIGHT if name == "light" else _DARK


def _build_qss() -> str:
    return f"""
/* Base ----------------------------------------------------------- */

QWidget {{
    background-color: transparent;
    color: {TEXT};
    font-family: "Geist", "Inter", "Segoe UI", "Cantarell", sans-serif;
    font-size: 10pt;
}}

/* Declared after the generic QWidget rule above so it wins the Qt
stylesheet cascade tie (equal-specificity type selectors resolve to
"last rule wins"). Otherwise QDialog/QMainWindow windows fall through
to "transparent" and pick up a native/system background instead of
the theme's BG - invisible in dark mode by coincidence, but breaks
light mode outright. */
QMainWindow, QDialog, QWidget#chrome {{
    background-color: {BG};
    color: {TEXT};
}}
QMainWindow {{
    border: 4px solid {WINDOW_EDGE};
}}

QToolTip {{
    color: {TEXT};
    background-color: {SURFACE_2};
    border: 1px solid {BORDER_HEX_STRONG};
    padding: 4px 6px;
}}

/* Titlebar ------------------------------------------------------- */

QFrame#titlebar {{
    background-color: {BG};
    border-bottom: 1px solid {BORDER_HEX};
    min-height: 38px;
    max-height: 38px;
}}
QLabel#titlebarTitle {{
    color: {TEXT_DIM};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 9pt;
}}
QLabel#titlebarTitle[role="primary"] {{ color: {TEXT}; }}
QLabel#titlebarVer {{
    color: {TEXT_FAINT};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 9pt;
}}
QFrame#titlebarMark {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_HEX_STRONG};
    border-radius: 6px;
    min-width: 22px; max-width: 22px;
    min-height: 22px; max-height: 22px;
}}
QPushButton#winBtn {{
    background-color: transparent;
    color: {TEXT_FAINT};
    border: none;
    border-radius: 6px;
    min-width: 30px; max-width: 30px;
    min-height: 26px; max-height: 26px;
    font-size: 11pt;
    padding: 0;
}}
QPushButton#winBtn:hover {{
    background-color: {SURFACE};
    color: {TEXT};
}}
QPushButton#winBtnClose:hover {{
    background-color: {CLOSE_HOVER_BG};
    color: {CLOSE_HOVER_FG};
}}
QToolButton#themeBtn {{
    background-color: transparent;
    color: {TEXT_DIM};
    border: none;
    border-radius: 6px;
}}
QToolButton#themeBtn:hover {{
    background-color: {SURFACE_3};
    color: {TEXT};
}}

/* Hero / titles -------------------------------------------------- */

QLabel[role="hero-h1"] {{
    color: {TEXT};
    font-size: 18pt;
    font-weight: 600;
    letter-spacing: -0.5px;
}}
QLabel[role="hero-sub"] {{
    color: {TEXT_DIM};
    font-size: 10pt;
}}
QLabel[role="section-label"] {{
    color: {TEXT_FAINT};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 8pt;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QLabel[role="muted"] {{ color: {TEXT_DIM}; }}
QLabel[role="faint"] {{ color: {TEXT_FAINT}; }}
QLabel[role="warn"] {{ color: {WARN}; }}
QLabel[role="error"] {{ color: {REC}; }}
QLabel[role="mono"] {{
    color: {TEXT_DIM};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 9pt;
}}
QLabel[role="empty-title"] {{
    color: {TEXT_DIM};
    font-size: 12pt;
    font-weight: 500;
}}
QLabel[role="empty-sub"] {{
    color: {TEXT_FAINT};
    font-size: 9.5pt;
}}

/* Status pill ---------------------------------------------------- */

QLabel#statusPill {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
    border: 1px solid {ACCENT_RING};
    border-radius: 12px;
    padding: 4px 12px;
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 8pt;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel#statusPill[state="paused"] {{
    background-color: {WARN_SOFT};
    color: {WARN};
    border-color: {WARN_RING};
}}
QLabel#statusPill[state="error"] {{
    background-color: {REC_SOFT};
    color: {REC};
    border-color: {REC_RING};
}}
QLabel#statusPill[state="off"] {{
    background-color: {OFF_PILL_BG};
    color: {TEXT_FAINT};
    border-color: {BORDER_HEX};
}}

/* Section block -------------------------------------------------- */

QFrame[role="section"] {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_HEX};
    border-radius: 12px;
}}

/* Stats strip ---------------------------------------------------- */

QFrame#statsStrip {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_HEX};
    border-radius: 10px;
}}
QFrame#statCell {{
    background-color: transparent;
    border-right: 1px solid {BORDER_HEX};
}}
QFrame#statCellLast {{ background-color: transparent; }}
QLabel#statKey {{
    color: {TEXT_FAINT};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 7.5pt;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel#statValue {{
    color: {TEXT};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 11pt;
}}

/* Buttons -------------------------------------------------------- */

QPushButton {{
    background-color: {SURFACE_2};
    color: {TEXT_DIM};
    border: 1px solid {BORDER_HEX};
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 9.5pt;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {SURFACE_3};
    color: {TEXT};
    border-color: {BORDER_HEX_STRONG};
}}
QPushButton:disabled {{
    background-color: {SURFACE};
    color: {TEXT_FAINT};
    border-color: {BORDER_HEX};
}}

QPushButton[kind="accent"] {{
    background-color: {ACCENT};
    color: {ACCENT_INK};
    border: 1px solid {BORDER_STRONG};
    font-weight: 600;
}}
QPushButton[kind="accent"]:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton[kind="accent"]:disabled {{
    background-color: {ACCENT_HEX_DIM};
    color: {TEXT_FAINT};
}}

QPushButton[kind="danger"] {{
    background-color: {REC};
    color: #fff;
    border: 1px solid {BORDER_STRONG};
    font-weight: 600;
}}
QPushButton[kind="danger"]:hover {{
    background-color: {REC_HOVER};
}}

QPushButton[kind="outline"] {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
    border: 1px solid {ACCENT_RING};
}}
QPushButton[kind="outline"]:hover {{
    background-color: {ACCENT_RING};
    color: {ACCENT_INK};
}}

QPushButton#iconBtn {{
    background-color: {SURFACE_2};
    color: {TEXT_DIM};
    border: 1px solid {BORDER_HEX};
    border-radius: 8px;
    min-width: 32px; max-width: 32px;
    min-height: 32px; max-height: 32px;
    padding: 0;
}}
QPushButton#iconBtn:hover {{
    color: {TEXT};
    border-color: {BORDER_HEX_STRONG};
    background-color: {ICON_BTN_HOVER_BG};
}}

/* Inputs --------------------------------------------------------- */

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QTimeEdit {{
    background-color: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER_HEX};
    border-radius: 8px;
    padding: 4px 10px;
    min-height: 22px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_INK};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 9.5pt;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {{
    border-color: {ACCENT};
    background-color: {SURFACE_3};
}}
QSpinBox::up-button, QSpinBox::down-button,
QTimeEdit::up-button, QTimeEdit::down-button {{
    background-color: transparent;
    border: none;
    width: 14px;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER_HEX_STRONG};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT};
}}

/* Checkbox ------------------------------------------------------- */

QCheckBox {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_HEX_STRONG};
    background-color: {SURFACE};
    border-radius: 4px;
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* Tree / table --------------------------------------------------- */

QTreeView, QTreeWidget {{
    background-color: {SURFACE};
    alternate-background-color: {ROW_ALT};
    color: {TEXT};
    border: 1px solid {BORDER_HEX};
    border-radius: 12px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT};
    show-decoration-selected: 1;
    outline: 0;
}}
QHeaderView::section {{
    background-color: {SURFACE};
    color: {TEXT_FAINT};
    border: none;
    border-bottom: 1px solid {BORDER_HEX};
    padding: 8px 10px;
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 8pt;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QTreeView::item, QTreeWidget::item {{
    padding: 7px 4px;
    border: none;
    border-bottom: 1px solid {BORDER_HEX};
}}
QTreeView::item:selected, QTreeWidget::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {TEXT};
}}

/* Progress bar --------------------------------------------------- */

QProgressBar {{
    background-color: {SURFACE_2};
    border: 1px solid {BORDER_HEX};
    border-radius: 5px;
    text-align: center;
    color: {TEXT_DIM};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 8.5pt;
    height: 16px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
    margin: 1px;
}}

/* Slider --------------------------------------------------------- */

QSlider::groove:horizontal {{
    background: {SURFACE_2};
    height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px; margin: -6px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* Scrollbar ------------------------------------------------------ */

QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle {{
    background: {SCROLLBAR_HANDLE};
    border-radius: 5px;
    min-width: 24px; min-height: 24px;
}}
QScrollBar::handle:hover {{ background: {SCROLLBAR_HANDLE_HOVER}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Menu ----------------------------------------------------------- */

QMenu {{
    background-color: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER_HEX_STRONG};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {ACCENT};
}}
QMenu::separator {{
    background-color: {BORDER_HEX};
    height: 1px;
    margin: 4px 8px;
}}

/* Footer --------------------------------------------------------- */

QFrame#footer {{
    background-color: {BG};
    border-top: 1px solid {BORDER_HEX};
    min-height: 44px;
    max-height: 44px;
}}
QLabel#footerLabel {{
    color: {TEXT_FAINT};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 8pt;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QLabel#footerKey {{
    color: {TEXT_DIM};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 9pt;
}}
QLabel#footerKey b {{ color: {TEXT}; font-weight: 500; }}
QLabel#footerPlatform {{
    color: {TEXT_FAINT};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 9pt;
}}
QPushButton#folderChip {{
    background-color: transparent;
    color: {TEXT_FAINT};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 8.5pt;
    text-align: left;
}}
QPushButton#folderChip:hover {{
    color: {ACCENT};
    border-color: {BORDER_HEX};
    background-color: {SURFACE};
}}

/* Group box (used in dialogs) ----------------------------------- */

QGroupBox {{
    border: 1px solid {BORDER_HEX};
    border-radius: 10px;
    margin-top: 16px;
    padding: 14px 12px 10px 12px;
    color: {TEXT_FAINT};
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 8pt;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}}

/* Info badge (small "i" with tooltip) --------------------------- */

QLabel#infoBadge {{
    color: {TEXT_FAINT};
    background-color: {SURFACE_2};
    border: 1px solid {BORDER_HEX_STRONG};
    border-radius: 10px;
    font-family: "Geist Mono", "JetBrains Mono", monospace;
    font-size: 9pt;
    font-style: italic;
}}
QLabel#infoBadge:hover {{
    color: {ACCENT};
    border-color: {ACCENT_RING};
}}

/* Dialog header label ------------------------------------------- */

QLabel#dialogTitle {{
    color: {TEXT};
    font-size: 13pt;
    font-weight: 600;
    letter-spacing: -0.3px;
}}
QLabel#dialogSubtitle {{
    color: {TEXT_DIM};
    font-size: 9.5pt;
}}
"""


# Initial bind: dark.
_apply(_DARK)
QSS = _build_qss()


def set_theme(name: str) -> str:
    """Switch the active palette and return the freshly built QSS string.

    Caller is responsible for re-applying the QSS to the QApplication and
    re-polishing widgets that read palette values lazily."""
    global THEME, QSS
    name = "light" if name == "light" else "dark"
    THEME = name
    _apply(_palette_for(name))
    QSS = _build_qss()
    return QSS
