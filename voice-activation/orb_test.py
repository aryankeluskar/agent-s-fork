#!/usr/bin/env python3
"""
Standalone animated orb test
Shows the WebGL-style orb in a window for testing
"""

import sys
import time
import ctypes
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QOpenGLWidget, QVBoxLayout, QLabel, QSlider
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QSurfaceFormat
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader


class AnimatedOrb(QOpenGLWidget):
    """OpenGL widget that renders an animated orb using shaders"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Set OpenGL format before initialization
        fmt = QSurfaceFormat()
        fmt.setVersion(4, 1)  # macOS supports up to OpenGL 4.1
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        fmt.setSamples(4)  # Anti-aliasing
        self.setFormat(fmt)

        self.start_time = time.time()
        self.hue = 0.0
        self.hover = 0.0
        self.rotation = 0.0
        self.hover_intensity = 0.2
        self.shader_program = None
        self.vao = None
        self.vbo = None

        # Animation timer - will start after GL is initialized
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.animation_started = False

    def initializeGL(self):
        """Initialize OpenGL context and shaders"""
        print(f"OpenGL Version: {glGetString(GL_VERSION).decode()}")
        print(f"GLSL Version: {glGetString(GL_SHADING_LANGUAGE_VERSION).decode()}")

        glClearColor(0.0, 0.0, 0.0, 1.0)  # Black background for testing
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Vertex shader - using 410 core for macOS compatibility
        vertex_shader = """
        #version 410 core
        layout(location = 0) in vec2 position;
        layout(location = 1) in vec2 uv;
        out vec2 vUv;

        void main() {
            vUv = uv;
            gl_Position = vec4(position, 0.0, 1.0);
        }
        """

        # Fragment shader (ported from the JS code)
        fragment_shader = """
        #version 410 core

        uniform float iTime;
        uniform vec3 iResolution;
        uniform float hue;
        uniform float hover;
        uniform float rot;
        uniform float hoverIntensity;
        uniform vec3 backgroundColor;

        in vec2 vUv;
        out vec4 FragColor;

        vec3 rgb2yiq(vec3 c) {
            float y = dot(c, vec3(0.299, 0.587, 0.114));
            float i = dot(c, vec3(0.596, -0.274, -0.322));
            float q = dot(c, vec3(0.211, -0.523, 0.312));
            return vec3(y, i, q);
        }

        vec3 yiq2rgb(vec3 c) {
            float r = c.x + 0.956 * c.y + 0.621 * c.z;
            float g = c.x - 0.272 * c.y - 0.647 * c.z;
            float b = c.x - 1.106 * c.y + 1.703 * c.z;
            return vec3(r, g, b);
        }

        vec3 adjustHue(vec3 color, float hueDeg) {
            float hueRad = hueDeg * 3.14159265 / 180.0;
            vec3 yiq = rgb2yiq(color);
            float cosA = cos(hueRad);
            float sinA = sin(hueRad);
            float i = yiq.y * cosA - yiq.z * sinA;
            float q = yiq.y * sinA + yiq.z * cosA;
            yiq.y = i;
            yiq.z = q;
            return yiq2rgb(yiq);
        }

        vec3 hash33(vec3 p3) {
            p3 = fract(p3 * vec3(0.1031, 0.11369, 0.13787));
            p3 += dot(p3, p3.yxz + 19.19);
            return -1.0 + 2.0 * fract(vec3(
                p3.x + p3.y,
                p3.x + p3.z,
                p3.y + p3.z
            ) * p3.zyx);
        }

        float snoise3(vec3 p) {
            const float K1 = 0.333333333;
            const float K2 = 0.166666667;
            vec3 i = floor(p + (p.x + p.y + p.z) * K1);
            vec3 d0 = p - (i - (i.x + i.y + i.z) * K2);
            vec3 e = step(vec3(0.0), d0 - d0.yzx);
            vec3 i1 = e * (1.0 - e.zxy);
            vec3 i2 = 1.0 - e.zxy * (1.0 - e);
            vec3 d1 = d0 - (i1 - K2);
            vec3 d2 = d0 - (i2 - K1);
            vec3 d3 = d0 - 0.5;
            vec4 h = max(0.6 - vec4(
                dot(d0, d0),
                dot(d1, d1),
                dot(d2, d2),
                dot(d3, d3)
            ), 0.0);
            vec4 n = h * h * h * h * vec4(
                dot(d0, hash33(i)),
                dot(d1, hash33(i + i1)),
                dot(d2, hash33(i + i2)),
                dot(d3, hash33(i + 1.0))
            );
            return dot(vec4(31.316), n);
        }

        vec4 extractAlpha(vec3 colorIn) {
            float a = max(max(colorIn.r, colorIn.g), colorIn.b);
            return vec4(colorIn.rgb / (a + 1e-5), a);
        }

        const vec3 baseColor1 = vec3(0.611765, 0.262745, 0.996078);
        const vec3 baseColor2 = vec3(0.298039, 0.760784, 0.913725);
        const vec3 baseColor3 = vec3(0.062745, 0.078431, 0.600000);
        const float innerRadius = 0.6;
        const float noiseScale = 0.65;

        float light1(float intensity, float attenuation, float dist) {
            return intensity / (1.0 + dist * attenuation);
        }

        float light2(float intensity, float attenuation, float dist) {
            return intensity / (1.0 + dist * dist * attenuation);
        }

        vec4 draw(vec2 uv) {
            vec3 color1 = adjustHue(baseColor1, hue);
            vec3 color2 = adjustHue(baseColor2, hue);
            vec3 color3 = adjustHue(baseColor3, hue);

            float ang = atan(uv.y, uv.x);
            float len = length(uv);
            float invLen = len > 0.0 ? 1.0 / len : 0.0;

            float bgLuminance = dot(backgroundColor, vec3(0.299, 0.587, 0.114));

            float n0 = snoise3(vec3(uv * noiseScale, iTime * 0.5)) * 0.5 + 0.5;
            float r0 = mix(mix(innerRadius, 1.0, 0.4), mix(innerRadius, 1.0, 0.6), n0);
            float d0 = distance(uv, (r0 * invLen) * uv);
            float v0 = light1(1.0, 10.0, d0);

            v0 *= smoothstep(r0 * 1.05, r0, len);
            float innerFade = smoothstep(r0 * 0.8, r0 * 0.95, len);
            v0 *= mix(innerFade, 1.0, bgLuminance * 0.7);
            float cl = cos(ang + iTime * 2.0) * 0.5 + 0.5;

            float a = iTime * -1.0;
            vec2 pos = vec2(cos(a), sin(a)) * r0;
            float d = distance(uv, pos);
            float v1 = light2(1.5, 5.0, d);
            v1 *= light1(1.0, 50.0, d0);

            float v2 = smoothstep(1.0, mix(innerRadius, 1.0, n0 * 0.5), len);
            float v3 = smoothstep(innerRadius, mix(innerRadius, 1.0, 0.5), len);

            vec3 colBase = mix(color1, color2, cl);
            float fadeAmount = mix(1.0, 0.1, bgLuminance);

            vec3 darkCol = mix(color3, colBase, v0);
            darkCol = (darkCol + v1) * v2 * v3;
            darkCol = clamp(darkCol, 0.0, 1.0);

            vec3 lightCol = (colBase + v1) * mix(1.0, v2 * v3, fadeAmount);
            lightCol = mix(backgroundColor, lightCol, v0);
            lightCol = clamp(lightCol, 0.0, 1.0);

            vec3 finalCol = mix(darkCol, lightCol, bgLuminance);

            return extractAlpha(finalCol);
        }

        vec4 mainImage(vec2 fragCoord) {
            vec2 center = iResolution.xy * 0.5;
            float size = min(iResolution.x, iResolution.y);
            vec2 uv = (fragCoord - center) / size * 2.0;

            float angle = rot;
            float s = sin(angle);
            float c = cos(angle);
            uv = vec2(c * uv.x - s * uv.y, s * uv.x + c * uv.y);

            uv.x += hover * hoverIntensity * 0.1 * sin(uv.y * 10.0 + iTime);
            uv.y += hover * hoverIntensity * 0.1 * sin(uv.x * 10.0 + iTime);

            return draw(uv);
        }

        void main() {
            vec2 fragCoord = vUv * iResolution.xy;
            vec4 col = mainImage(fragCoord);
            FragColor = vec4(col.rgb * col.a, col.a);
        }
        """

        try:
            # Compile shaders
            vertex = compileShader(vertex_shader, GL_VERTEX_SHADER)
            fragment = compileShader(fragment_shader, GL_FRAGMENT_SHADER)

            # Create program and link (skip validation during init)
            self.shader_program = glCreateProgram()
            glAttachShader(self.shader_program, vertex)
            glAttachShader(self.shader_program, fragment)
            glLinkProgram(self.shader_program)

            # Check link status
            link_status = glGetProgramiv(self.shader_program, GL_LINK_STATUS)
            if not link_status:
                info_log = glGetProgramInfoLog(self.shader_program)
                print(f"Shader linking error: {info_log.decode()}")
                return

            print("Shaders compiled and linked successfully!")
        except Exception as e:
            print(f"Shader compilation error: {e}")
            import traceback
            traceback.print_exc()
            return

        # Create fullscreen triangle
        vertices = np.array([
            # positions    # uvs
            -1.0, -1.0,   0.0, 0.0,
             3.0, -1.0,   2.0, 0.0,
            -1.0,  3.0,   0.0, 2.0,
        ], dtype=np.float32)

        # Create VAO and VBO
        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)

        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        # Position attribute
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * 4, ctypes.c_void_p(0))

        # UV attribute
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * 4, ctypes.c_void_p(8))

        glBindVertexArray(0)

        # Start animation timer now that GL is initialized
        if not self.animation_started:
            self.timer.start(16)  # ~60 FPS
            self.animation_started = True
            print("Animation started!")

    def resizeGL(self, w, h):
        """Handle resize events"""
        glViewport(0, 0, w, h)

    def paintGL(self):
        """Render the orb"""
        if not self.shader_program:
            print("WARNING: No shader program!")
            return

        glClear(GL_COLOR_BUFFER_BIT)

        # Check for OpenGL errors
        error = glGetError()
        if error != GL_NO_ERROR:
            print(f"OpenGL error before render: {error}")

        glUseProgram(self.shader_program)

        # Update uniforms
        current_time = time.time() - self.start_time

        # Get uniform locations and set values
        time_loc = glGetUniformLocation(self.shader_program, "iTime")
        glUniform1f(time_loc, current_time)

        res_loc = glGetUniformLocation(self.shader_program, "iResolution")
        w, h = float(self.width()), float(self.height())
        glUniform3f(res_loc, w, h, w / h if h > 0 else 1.0)

        hue_loc = glGetUniformLocation(self.shader_program, "hue")
        glUniform1f(hue_loc, self.hue)

        hover_loc = glGetUniformLocation(self.shader_program, "hover")
        glUniform1f(hover_loc, self.hover)

        rot_loc = glGetUniformLocation(self.shader_program, "rot")
        glUniform1f(rot_loc, self.rotation)

        hover_intensity_loc = glGetUniformLocation(self.shader_program, "hoverIntensity")
        glUniform1f(hover_intensity_loc, self.hover_intensity)

        bg_loc = glGetUniformLocation(self.shader_program, "backgroundColor")
        glUniform3f(bg_loc, 0.0, 0.0, 0.0)

        # Draw
        glBindVertexArray(self.vao)
        glDrawArrays(GL_TRIANGLES, 0, 3)
        glBindVertexArray(0)

        # Check for OpenGL errors after render
        error = glGetError()
        if error != GL_NO_ERROR:
            print(f"OpenGL error after render: {error}")

    def set_hover(self, value):
        """Set hover intensity (0.0 to 1.0)"""
        self.hover = max(0.0, min(1.0, value))

    def set_hue(self, value):
        """Set hue shift in degrees"""
        self.hue = value


class OrbTestWindow(QWidget):
    """Test window for the animated orb"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Animated Orb Test")
        self.resize(400, 500)

        # Create layout
        layout = QVBoxLayout()

        # Create orb
        self.orb = AnimatedOrb()
        self.orb.setMinimumSize(400, 400)
        layout.addWidget(self.orb)

        # Add hover slider
        hover_label = QLabel("Hover Intensity (simulates volume):")
        layout.addWidget(hover_label)

        self.hover_slider = QSlider(Qt.Horizontal)
        self.hover_slider.setMinimum(0)
        self.hover_slider.setMaximum(100)
        self.hover_slider.setValue(0)
        self.hover_slider.valueChanged.connect(self.on_hover_changed)
        layout.addWidget(self.hover_slider)

        self.hover_value_label = QLabel("0%")
        layout.addWidget(self.hover_value_label)

        # Add hue slider
        hue_label = QLabel("Hue Shift:")
        layout.addWidget(hue_label)

        self.hue_slider = QSlider(Qt.Horizontal)
        self.hue_slider.setMinimum(-180)
        self.hue_slider.setMaximum(180)
        self.hue_slider.setValue(0)
        self.hue_slider.valueChanged.connect(self.on_hue_changed)
        layout.addWidget(self.hue_slider)

        self.hue_value_label = QLabel("0°")
        layout.addWidget(self.hue_value_label)

        self.setLayout(layout)

    def on_hover_changed(self, value):
        """Update hover intensity"""
        hover = value / 100.0
        self.orb.set_hover(hover)
        self.hover_value_label.setText(f"{value}%")

    def on_hue_changed(self, value):
        """Update hue shift"""
        self.orb.set_hue(value)
        self.hue_value_label.setText(f"{value}°")


def main():
    app = QApplication(sys.argv)
    window = OrbTestWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
