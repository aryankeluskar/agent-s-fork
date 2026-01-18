#!/usr/bin/env python3
"""
Orb test using WebView - transparent overlay with your existing WebGL code
"""

import sys
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtGui import QColor

class TransparentWebView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))  # Transparent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

class OrbWindow(QWidget):
    def __init__(self, port=8765):
        super().__init__()

        # Window flags for transparent overlay
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("background: transparent; border: none;")

        # Create web view
        self.web_view = TransparentWebView(self)

        # Load the orb HTML from local server
        self.web_view.load(QUrl(f'http://localhost:{port}/orb.html'))

        # Set size to small orb (you can adjust)
        orb_size = 200
        self.resize(orb_size, orb_size)
        self.web_view.setGeometry(0, 0, orb_size, orb_size)

        # Position in center of screen for testing
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - orb_size) // 2,
            (screen.height() - orb_size) // 2
        )

    def set_hover(self, value):
        """Update the orb's hover effect (0.0 to 1.0)"""
        js_code = f"if (window.setHover) window.setHover({value});"
        self.web_view.page().runJavaScript(js_code)

def start_server(port=8765):
    """Start a simple HTTP server in the background"""
    # Change to the script directory so we can serve orb.html
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Suppress log messages

    server = HTTPServer(('localhost', port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"HTTP server started on http://localhost:{port}")
    return server

def main():
    port = 8765

    # Start local HTTP server
    server = start_server(port)

    app = QApplication(sys.argv)
    window = OrbWindow(port=port)
    window.show()

    print("Orb window shown! Should see animated purple/blue orb.")
    print("Hover over the orb to see effects!")
    print("Close the window or press Ctrl+C to exit.")

    try:
        sys.exit(app.exec_())
    finally:
        server.shutdown()

if __name__ == "__main__":
    main()
