"""
Transparent Overlay UI

PyQt5-based transparent overlay window for displaying:
- Animated orb visualization
- Real-time transcription text
- Voice activity indicators
"""

import os
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QRect, QUrl, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QLinearGradient


# Path to assets
ASSETS_DIR = Path(__file__).parent / "assets"


class TransparentWebView(QWebEngineView):
    """Transparent WebView for rendering the orb."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

    def set_hover(self, value: float):
        """Set hover intensity (0.0 to 1.0)."""
        js_code = f"if (window.setHover) window.setHover({value});"
        self.page().runJavaScript(js_code)


class TranscriptionSignals(QObject):
    """Signals for thread-safe UI updates."""
    show_overlay = pyqtSignal()
    hide_overlay = pyqtSignal()
    update_text = pyqtSignal(str)
    update_volume = pyqtSignal(float)


class TransparentOverlay(QWidget):
    """Transparent overlay window showing transcription."""

    def __init__(self, http_port: int = 8765):
        super().__init__()
        self.http_port = http_port
        self.signals = TranscriptionSignals()

        # Connect signals
        self.signals.show_overlay.connect(self.show_ui)
        self.signals.hide_overlay.connect(self.hide_ui)
        self.signals.update_text.connect(self.update_transcription)
        self.signals.update_volume.connect(self.update_volume_level)

        # State
        self.transcription_text = ""
        self.placeholder_text = "Say something..."
        self.volume_level = 0.0
        self.is_visible = False
        self.macos_level_set = False

        # UI configuration
        self.padding_x = 13
        self.padding_y = 10
        self.orb_size = 26
        self.orb_spacing = 10
        self.orb_fixed_y = self.padding_y + (self.orb_size // 2)
        self.font_size = 13
        self.max_width = 400
        self.min_width = 224
        self.corner_radius = 26

        # Colors
        self.text_color = QColor(255, 255, 255, 255)
        self.placeholder_color = QColor(255, 255, 255, 140)

        # Gradient colors for animation
        self.gradient_color1_start = QColor(10, 10, 15)
        self.gradient_color1_end = QColor(25, 15, 35)
        self.gradient_color2_start = QColor(15, 10, 20)
        self.gradient_color2_end = QColor(40, 25, 50)

        # Animation state
        self.animation_time = 0.0
        self.gradient_timer = QTimer()
        self.gradient_timer.timeout.connect(self.animate_gradient)
        self.gradient_timer.start(50)

        # Hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.auto_hide)

        # Orb widget
        self.orb = None

        self.setup_ui()

    def setup_ui(self):
        """Setup the transparent overlay window."""
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.WindowDoesNotAcceptFocus |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("background: transparent; border: none;")
        self.setWindowOpacity(1.0)

        # Create animated orb WebView
        self.orb = TransparentWebView(self)
        self.orb.setFixedSize(self.orb_size, self.orb_size)
        self.orb.move(self.padding_x, self.orb_fixed_y - (self.orb_size // 2))

        # Load orb from local HTTP server
        self.orb.load(QUrl(f'http://localhost:{self.http_port}/orb.html'))

        # Set initial size
        self.resize(self.max_width, 60)

        # Position in top right corner
        screen = QApplication.primaryScreen().geometry()
        margin = 20
        self.move(screen.width() - self.max_width - margin, margin)

        # Start hidden
        self.hide()

    def show_ui(self):
        """Show the overlay."""
        self.is_visible = True
        self.transcription_text = ""
        self.volume_level = 0.0
        self.show()
        self.raise_()
        self.activateWindow()

        # macOS specific: Set window level to appear over fullscreen apps
        if not self.macos_level_set:
            try:
                from ctypes import c_void_p
                import objc
                from Cocoa import NSScreenSaverWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary, NSWindowCollectionBehaviorFullScreenAuxiliary

                nsview_id = self.winId().__int__()
                nsview = objc.objc_object(c_void_p=nsview_id)
                nswindow = nsview.window()

                if nswindow:
                    nswindow.setLevel_(NSScreenSaverWindowLevel + 1)
                    behavior = (
                        NSWindowCollectionBehaviorCanJoinAllSpaces |
                        NSWindowCollectionBehaviorStationary |
                        NSWindowCollectionBehaviorFullScreenAuxiliary
                    )
                    nswindow.setCollectionBehavior_(behavior)
                    self.macos_level_set = True
            except Exception as e:
                pass  # Non-macOS or missing dependencies

        self.update_geometry()

    def hide_ui(self):
        """Hide the overlay."""
        self.is_visible = False
        self.transcription_text = ""
        self.hide()

    def auto_hide(self):
        """Auto-hide after delay."""
        self.signals.hide_overlay.emit()

    def schedule_auto_hide(self, delay_ms: int = 2500):
        """Schedule auto-hide after delay."""
        self.hide_timer.start(delay_ms)

    def update_transcription(self, text: str):
        """Update transcription text."""
        self.transcription_text = text
        self.update_geometry()
        self.update()

        # Schedule auto-hide when transcription is complete
        if text and not text.endswith("..."):
            self.schedule_auto_hide()

    def update_volume_level(self, level: float):
        """Update volume level (0.0 to 1.0)."""
        self.volume_level = max(0.0, min(1.0, level))
        if self.orb:
            self.orb.set_hover(self.volume_level)
        self.update()

    def animate_gradient(self):
        """Animate the background gradient."""
        self.animation_time += 0.05
        self.update()

    def update_geometry(self):
        """Update window size based on content."""
        if not self.is_visible:
            return

        font = QFont(".AppleSystemUIFont", self.font_size)
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.PercentageSpacing, 98)
        metrics = QApplication.fontMetrics()
        metrics = metrics.__class__(font)

        text_width = min(
            self.max_width - (self.padding_x * 2) - self.orb_size - self.orb_spacing,
            metrics.horizontalAdvance(self.transcription_text)
        )

        if text_width < self.min_width - (self.padding_x * 2) - self.orb_size - self.orb_spacing:
            text_width = self.min_width - (self.padding_x * 2) - self.orb_size - self.orb_spacing

        # Word wrap
        words = self.transcription_text.split()
        lines = []
        current_line = []
        current_width = 0

        for word in words:
            word_width = metrics.horizontalAdvance(word + " ")
            if current_width + word_width > text_width and current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_width = word_width
            else:
                current_line.append(word)
                current_width += word_width

        if current_line:
            lines.append(" ".join(current_line))

        line_height = metrics.height()
        text_height = len(lines) * line_height if lines else line_height

        width = text_width + (self.padding_x * 2) + self.orb_size + self.orb_spacing
        min_height = self.orb_size + (self.padding_y * 2)
        height = max(text_height + (self.padding_y * 2), min_height)

        screen = QApplication.primaryScreen().geometry()
        margin = 20
        self.setGeometry(
            screen.width() - width - margin,
            margin,
            width,
            height
        )

    def paintEvent(self, _event):
        """Custom paint event for rounded rectangle with transparency."""
        if not self.is_visible:
            return

        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        # Animated gradient
        t = (math.sin(self.animation_time * 0.3) + 1) / 2

        def lerp_color(c1, c2, t):
            return QColor(
                int(c1.red() + (c2.red() - c1.red()) * t),
                int(c1.green() + (c2.green() - c1.green()) * t),
                int(c1.blue() + (c2.blue() - c1.blue()) * t),
                250
            )

        color_start = lerp_color(self.gradient_color1_start, self.gradient_color2_start, t)
        color_end = lerp_color(self.gradient_color1_end, self.gradient_color2_end, t)

        gradient = QLinearGradient(QPointF(0, 0), QPointF(rect.width(), rect.height()))
        gradient.setColorAt(0, color_start)
        gradient.setColorAt(1, color_end)

        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.corner_radius, self.corner_radius)

        # Draw text
        font = QFont(".AppleSystemUIFont", self.font_size)
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.PercentageSpacing, 98)
        painter.setFont(font)

        text_x = int(self.padding_x + self.orb_size + self.orb_spacing)
        text_rect = QRect(
            text_x,
            self.padding_y,
            self.rect().width() - text_x - self.padding_x,
            self.rect().height() - (self.padding_y * 2)
        )

        if self.transcription_text:
            painter.setPen(QPen(self.text_color))
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                self.transcription_text
            )
        else:
            painter.setPen(QPen(self.placeholder_color))
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                self.placeholder_text
            )


def start_http_server(port: int = 8765) -> HTTPServer:
    """Start a simple HTTP server in the background for serving orb.html."""
    os.chdir(str(ASSETS_DIR))

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    server = HTTPServer(('localhost', port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
