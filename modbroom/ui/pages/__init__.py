"""Page base class shared by every ModBroom page."""
from PySide6.QtWidgets import QWidget, QVBoxLayout

from ..widgets import SectionHeader


class Page(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 20, 24, 20)
        self.layout_.setSpacing(12)

    @property
    def state(self):
        return self.window.state

    def header(self, title, subtitle=None):
        self.layout_.addWidget(SectionHeader(title, subtitle))

    def refresh(self):
        pass
