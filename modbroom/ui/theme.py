"""One dark theme, Fusion style, no stylesheets to maintain."""

BG       = '#14161a'
PANEL    = '#1b1e24'
PANEL2   = '#22262e'
PANEL3   = '#2b303a'
TEXT     = '#e8e6e1'
MUTED    = '#9a978f'
ACCENT   = '#3ddc84'
ACCENT_D = '#2bb56a'
WARN     = '#e8b33f'
BAD      = '#e5534b'
GOOD     = '#3ddc84'
BORDER   = '#2e333d'

QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QMainWindow {{ background: {BG}; }}
QFrame#sidebar {{ background: {PANEL}; border: none; border-right: 1px solid {BORDER}; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#card:hover {{ border-color: {PANEL3}; }}
QLabel#h1 {{ font-size: 22px; font-weight: 600; color: {TEXT}; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#statNumber {{ font-size: 30px; font-weight: 700; color: {TEXT}; }}
QLabel#statLabel {{ color: {MUTED}; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }}
QPushButton {{
    background: {PANEL3}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 14px; color: {TEXT};
}}
QPushButton:hover {{ background: #343a46; }}
QPushButton:pressed {{ background: {PANEL2}; }}
QPushButton#primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: #0d2018; font-weight: 700; }}
QPushButton#primary:hover {{ background: #4aef8f; }}
QPushButton#primary:disabled {{ background: {PANEL3}; color: {MUTED}; border-color: {BORDER}; }}
QPushButton#danger {{ background: transparent; border: 1px solid {BAD}; color: #ff9d97; }}
QPushButton#danger:hover {{ background: #3a2222; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {BORDER}; color: {TEXT}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 9px; selection-background-color: {ACCENT_D}; color: {TEXT};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {ACCENT_D}; }}
QComboBox, QSpinBox {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px; color: {TEXT};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QTreeWidget, QTableWidget, QListWidget {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
    alternate-background-color: #1f232b; gridline-color: {BORDER};
}}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
    background: #24402f; color: {TEXT};
}}
QHeaderView::section {{
    background: {PANEL2}; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 6px 8px; font-size: 11px;
}}
QProgressBar {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px;
    height: 10px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 8px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {PANEL3}; border-radius: 5px; min-height: 30px; }}
QTabBar::tab {{ padding: 8px 16px; border: none; background: transparent; color: {MUTED}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QToolTip {{ background: {PANEL3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
"""

SEVERITY_COLORS = {'high': BAD, 'medium': WARN, 'low': '#7aa2f7', 'info': MUTED}

def apply(app):
    from PySide6.QtGui import QPalette, QColor
    app.setStyle('Fusion')
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(PANEL))
    pal.setColor(QPalette.AlternateBase, QColor('#1f232b'))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(PANEL3))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor('#24402f'))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT))
    pal.setColor(QPalette.ToolTipBase, QColor(PANEL3))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(MUTED))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MUTED))
    pal.setColor(QPalette.PlaceholderText, QColor(MUTED))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
