#!/usr/bin/env python3
"""
Test the overlay UI with orb and transcription text
Shows what the actual voice assistant overlay looks like
"""

import sys
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QTimer, QUrl, QRect, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QLinearGradient

class TransparentWebView(QWebEngineView):
    """Transparent WebView for rendering the orb"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

    def set_hover(self, value):
        """Set hover intensity (0.0 to 1.0)"""
        js_code = f"if (window.setHover) window.setHover({value});"
        self.page().runJavaScript(js_code)


class OverlayPreview(QWidget):
    """Preview of the voice assistant overlay"""

    def __init__(self, http_port=8765):
        super().__init__()
        self.http_port = http_port

        # State
        self.transcription_text = "Lorem ipsum dolor sit amet pronesque vesque tesque"
        self.placeholder_text = "Say something..."
        self.volume_level = 0.0
        self.show_placeholder = False

        # UI configuration
        self.padding_x = 13  # Horizontal padding (left/right)
        self.padding_y = 10  # Vertical padding (top/bottom)
        self.orb_size = 26
        self.orb_spacing = 10
        self.orb_fixed_y = self.padding_y + (self.orb_size // 2)
        self.font_size = 13
        self.max_width = 400
        self.min_width = 224
        self.corner_radius = 26  # Smooth rounded corners for pill shape

        # Modern color scheme - animated gradient
        self.text_color = QColor(255, 255, 255, 255)
        self.placeholder_color = QColor(255, 255, 255, 140)

        # Gradient colors for animation
        self.gradient_color1_start = QColor(10, 10, 15)  # Very dark blue-black
        self.gradient_color1_end = QColor(25, 15, 35)    # Dark purple
        self.gradient_color2_start = QColor(15, 10, 20)  # Dark blue-purple
        self.gradient_color2_end = QColor(40, 25, 50)    # Purple

        self.setup_ui()

        # Animate the orb pulsing and gradient
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.animate)
        self.animation_timer.start(50)
        self.time = 0

    def setup_ui(self):
        """Setup the overlay window"""
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        # Create orb WebView at fixed vertical position (centered in initial height)
        self.orb = TransparentWebView(self)
        self.orb.setFixedSize(self.orb_size, self.orb_size)
        # Position orb at fixed Y position (will not move as text grows)
        self.orb.move(self.padding_x, self.orb_fixed_y - (self.orb_size // 2))
        self.orb.load(QUrl(f'http://localhost:{self.http_port}/orb.html'))

        # Position in top right corner
        screen = QApplication.primaryScreen().geometry()
        margin = 20

        self.update_geometry()
        self.move(screen.width() - self.width() - margin, margin)

        self.show()

    def update_geometry(self):
        """Update window size based on content"""
        # Calculate text size with system font (SF Pro on macOS)
        font = QFont(".AppleSystemUIFont", self.font_size)
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.PercentageSpacing, 98)
        metrics = QApplication.fontMetrics()
        metrics = metrics.__class__(font)

        # Calculate text dimensions
        text_width = min(self.max_width - (self.padding_x * 2) - self.orb_size - self.orb_spacing,
                        metrics.horizontalAdvance(self.transcription_text))

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

        # Calculate height
        line_height = metrics.height()
        text_height = len(lines) * line_height if lines else line_height

        # Window dimensions - ensure height is at least tall enough for the orb
        width = text_width + (self.padding_x * 2) + self.orb_size + self.orb_spacing
        min_height = self.orb_size + (self.padding_y * 2)
        height = max(text_height + (self.padding_y * 2), min_height)

        # Update size
        self.setFixedSize(width, height)

        # Orb stays at fixed position (do NOT update its position)

    def animate(self):
        """Animate the orb pulsing"""
        import math
        self.time += 0.05
        # Simulate voice volume with sine wave
        self.volume_level = (math.sin(self.time) + 1) / 2
        if self.orb:
            self.orb.set_hover(self.volume_level)
        self.update()

    def paintEvent(self, event):
        """Draw the overlay background and text"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        # Create animated gradient background
        import math

        # Calculate gradient colors based on animation time
        t = (math.sin(self.time * 0.3) + 1) / 2  # Smooth oscillation 0-1

        # Interpolate between color sets
        def lerp_color(c1, c2, t):
            return QColor(
                int(c1.red() + (c2.red() - c1.red()) * t),
                int(c1.green() + (c2.green() - c1.green()) * t),
                int(c1.blue() + (c2.blue() - c1.blue()) * t),
                250
            )

        color_start = lerp_color(self.gradient_color1_start, self.gradient_color2_start, t)
        color_end = lerp_color(self.gradient_color1_end, self.gradient_color2_end, t)

        # Create gradient from top-left to bottom-right
        from PyQt5.QtCore import QPointF
        gradient = QLinearGradient(QPointF(0, 0), QPointF(rect.width(), rect.height()))
        gradient.setColorAt(0, color_start)
        gradient.setColorAt(1, color_end)

        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.corner_radius, self.corner_radius)

        # Draw text with system font (SF Pro on macOS)
        font = QFont(".AppleSystemUIFont", self.font_size)
        font.setWeight(QFont.Medium)  # Slightly heavier weight for better readability
        font.setLetterSpacing(QFont.PercentageSpacing, 98)  # Tighter letter spacing
        painter.setFont(font)

        # Position text to the right of the orb
        text_x = int(self.padding_x + self.orb_size + self.orb_spacing)
        text_rect = QRect(
            text_x,
            self.padding_y,
            self.rect().width() - text_x - self.padding_x,
            self.rect().height() - (self.padding_y * 2)
        )

        if self.show_placeholder:
            painter.setPen(QPen(self.placeholder_color))
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                self.placeholder_text
            )
        else:
            painter.setPen(QPen(self.text_color))
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                self.transcription_text
            )

    def keyPressEvent(self, event):
        """Press space to toggle placeholder, Esc to quit"""
        if event.key() == Qt.Key_Space:
            self.show_placeholder = not self.show_placeholder
            self.update()
        elif event.key() == Qt.Key_Escape:
            QApplication.quit()


def start_http_server(port=8765):
    """Start HTTP server for orb.html"""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    server = HTTPServer(('localhost', port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"HTTP server started on http://localhost:{port}")
    return server


def main():
    port = 8765
    server = start_http_server(port)

    app = QApplication(sys.argv)
    overlay = OverlayPreview(http_port=port)

    print("Overlay preview shown!")
    print("- Pill-shaped overlay with darker background")
    print("- Orb has a subtle purple border for visual weight")
    print("- Press SPACE to toggle between transcription and placeholder")
    print("- Press ESC to quit")

    try:
        sys.exit(app.exec_())
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
