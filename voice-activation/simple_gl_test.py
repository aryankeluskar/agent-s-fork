#!/usr/bin/env python3
"""
Simple OpenGL test - just renders with a colored background
"""

import sys
from PyQt5.QtWidgets import QApplication, QWidget, QOpenGLWidget, QVBoxLayout
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QSurfaceFormat
from OpenGL.GL import *

class SimpleTriangle(QOpenGLWidget):
    def __init__(self):
        # Set format BEFORE calling super().__init__()
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)  # Use OpenGL 2.1 for maximum compatibility
        fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
        QSurfaceFormat.setDefaultFormat(fmt)

        super().__init__()
        self.setFormat(fmt)
        self.setMinimumSize(400, 400)
        self.frame_count = 0

    def initializeGL(self):
        print(f"OpenGL Version: {glGetString(GL_VERSION).decode()}")
        print(f"OpenGL Vendor: {glGetString(GL_VENDOR).decode()}")
        print(f"OpenGL Renderer: {glGetString(GL_RENDERER).decode()}")
        glClearColor(0.2, 0.6, 0.8, 1.0)  # Light blue
        print("initializeGL complete")

    def resizeGL(self, w, h):
        print(f"resizeGL called: {w}x{h}")
        glViewport(0, 0, w, h)

    def paintGL(self):
        self.frame_count += 1
        if self.frame_count % 60 == 0:  # Print every 60 frames
            print(f"paintGL called (frame {self.frame_count})")

        # Cycle through colors
        r = (self.frame_count % 255) / 255.0
        g = 0.3
        b = 0.8
        glClearColor(r, g, b, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        # Force flush
        glFlush()

def main():
    app = QApplication(sys.argv)

    # Create a window to hold the widget
    window = QWidget()
    window.setWindowTitle("Simple GL Test")
    layout = QVBoxLayout()

    widget = SimpleTriangle()
    layout.addWidget(widget)
    window.setLayout(layout)
    window.resize(400, 400)
    window.show()

    print("Window shown")

    # Update continuously
    timer = QTimer()
    timer.timeout.connect(widget.update)
    timer.start(16)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
