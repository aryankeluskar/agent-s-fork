#!/usr/bin/env python3
"""
Voice Assistant with Transparent Overlay UI
Features wake word detection and real-time transcription display
"""

import sys
import os
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
import pyaudio
import numpy as np
from openwakeword.model import Model
import whisper
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QRect, QUrl, QPointF
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


class TranscriptionSignals(QObject):
    """Signals for thread-safe UI updates"""
    show_overlay = pyqtSignal()
    hide_overlay = pyqtSignal()
    update_text = pyqtSignal(str)
    update_volume = pyqtSignal(float)


class TransparentOverlay(QWidget):
    """Transparent overlay window showing transcription"""

    def __init__(self, http_port=8765):
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
        self.volume_level = 0.0  # 0.0 to 1.0
        self.is_visible = False
        self.macos_level_set = False  # Track if macOS window level has been set

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

        # Animation state
        self.animation_time = 0.0
        self.gradient_timer = QTimer()
        self.gradient_timer.timeout.connect(self.animate_gradient)
        self.gradient_timer.start(50)  # Update every 50ms

        # Hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.auto_hide)

        # Create animated orb widget
        self.orb = None

        self.setup_ui()

    def setup_ui(self):
        """Setup the transparent overlay window"""
        # Window flags for transparency and always on top - CRITICAL for macOS
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

        # Set window level to floating (always on top)
        self.setWindowOpacity(1.0)

        # Create animated orb WebView at fixed vertical position
        self.orb = TransparentWebView(self)
        self.orb.setFixedSize(self.orb_size, self.orb_size)
        # Position orb at fixed Y position (will not move as text grows)
        self.orb.move(self.padding_x, self.orb_fixed_y - (self.orb_size // 2))

        # Load orb from local HTTP server
        self.orb.load(QUrl(f'http://localhost:{self.http_port}/orb.html'))

        # Set initial size
        self.resize(self.max_width, 60)

        # Position in top right corner
        screen = QApplication.primaryScreen().geometry()
        margin = 20
        self.move(screen.width() - self.max_width - margin, margin)

        print(f"DEBUG: Initial position: ({screen.width() - self.max_width - margin}, {margin})")
        print(f"DEBUG: Screen size: {screen.width()}x{screen.height()}")

        # Start hidden
        self.hide()

    def show_ui(self):
        """Show the overlay"""
        print("DEBUG: show_ui called")
        self.is_visible = True
        self.transcription_text = ""
        self.volume_level = 0.0
        self.show()
        self.raise_()
        self.activateWindow()

        # macOS specific: Set window level to appear over fullscreen apps (only once)
        if not self.macos_level_set:
            try:
                from ctypes import c_void_p, c_int
                import objc
                from Cocoa import NSApp, NSScreenSaverWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary, NSWindowCollectionBehaviorFullScreenAuxiliary
                from AppKit import NSView

                print(f"DEBUG: Attempting to set macOS window level...")

                # Get the native NSWindow from the view
                nsview_id = self.winId().__int__()
                print(f"DEBUG: Got view ID: {nsview_id}")

                nsview = objc.objc_object(c_void_p=nsview_id)
                print(f"DEBUG: Got nsview: {nsview}")

                # Get the window from the view
                nswindow = nsview.window()
                print(f"DEBUG: Got nswindow: {nswindow}")

                if nswindow:
                    print(f"DEBUG: Current window level: {nswindow.level()}")

                    # Use screen saver level to be above everything (CGShieldingWindowLevel)
                    nswindow.setLevel_(NSScreenSaverWindowLevel + 1)
                    print(f"DEBUG: Set window level to: {NSScreenSaverWindowLevel + 1}")

                    # Set collection behavior to appear on all spaces and over fullscreen
                    behavior = (
                        NSWindowCollectionBehaviorCanJoinAllSpaces |
                        NSWindowCollectionBehaviorStationary |
                        NSWindowCollectionBehaviorFullScreenAuxiliary
                    )
                    nswindow.setCollectionBehavior_(behavior)
                    print(f"DEBUG: Set collection behavior to: {behavior}")

                    self.macos_level_set = True
                    print("DEBUG: macOS window level set successfully")
                else:
                    print("DEBUG: Could not get NSWindow from view")
            except Exception as e:
                import traceback
                print(f"ERROR: Could not set macOS window level: {e}")
                print(traceback.format_exc())

        self.update_geometry()
        print(f"DEBUG: Window visible: {self.isVisible()}, geometry: {self.geometry()}")

    def hide_ui(self):
        """Hide the overlay"""
        self.is_visible = False
        self.transcription_text = ""
        self.hide()

    def auto_hide(self):
        """Auto-hide after delay"""
        self.signals.hide_overlay.emit()

    def schedule_auto_hide(self, delay_ms=2500):
        """Schedule auto-hide after delay"""
        self.hide_timer.start(delay_ms)

    def update_transcription(self, text):
        """Update transcription text"""
        self.transcription_text = text
        self.update_geometry()
        self.update()

        # Schedule auto-hide when transcription is complete
        if text and not text.endswith("..."):
            self.schedule_auto_hide()

    def update_volume_level(self, level):
        """Update volume level (0.0 to 1.0)"""
        self.volume_level = max(0.0, min(1.0, level))
        # Update orb hover effect based on volume
        if self.orb:
            self.orb.set_hover(self.volume_level)
        self.update()

    def animate_gradient(self):
        """Animate the background gradient"""
        self.animation_time += 0.05
        self.update()

    def update_geometry(self):
        """Update window size based on content"""
        if not self.is_visible:
            return

        # Calculate text size with system font (SF Pro on macOS)
        font = QFont(".AppleSystemUIFont", self.font_size)
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.PercentageSpacing, 98)
        metrics = QApplication.fontMetrics()
        metrics = metrics.__class__(font)

        # Calculate text dimensions with word wrap
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

        # Update size and position (keep in top right)
        screen = QApplication.primaryScreen().geometry()
        margin = 20
        self.setGeometry(
            screen.width() - width - margin,
            margin,
            width,
            height
        )

        # Orb stays at fixed position (do NOT update its position)

    def paintEvent(self, _event):
        """Custom paint event for rounded rectangle with transparency"""
        if not self.is_visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Use full rect
        rect = self.rect()

        # Create animated gradient background
        import math

        # Calculate gradient colors based on animation time
        t = (math.sin(self.animation_time * 0.3) + 1) / 2  # Smooth oscillation 0-1

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
        gradient = QLinearGradient(QPointF(0, 0), QPointF(rect.width(), rect.height()))
        gradient.setColorAt(0, color_start)
        gradient.setColorAt(1, color_end)

        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.corner_radius, self.corner_radius)

        # The orb is now drawn by the WebView widget, not here

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

        if self.transcription_text:
            # Draw actual transcription
            painter.setPen(QPen(self.text_color))
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
                self.transcription_text
            )
        else:
            # Draw placeholder
            painter.setPen(QPen(self.placeholder_color))
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                self.placeholder_text
            )


class VoiceAssistant:
    """Voice assistant with wake word detection and transcription"""

    def __init__(self, overlay, input_device_index=None):
        self.overlay = overlay

        # State
        self.is_running = False
        self.is_recording = False
        self.recorded_frames = []

        # Audio configuration
        self.CHUNK = 1280  # 80ms at 16kHz
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000

        # Pre-roll buffer (captures audio BEFORE wake word for smooth transition)
        self.pre_roll_buffer = []
        self.PRE_ROLL_CHUNKS = 5  # ~400ms of audio before wake word

        # Voice Activity Detection (VAD) settings
        self.SILENCE_THRESHOLD = 400  # RMS threshold for silence (adjust for your mic)
        self.MAX_SILENCE_CHUNKS = 18  # ~1.4 seconds of silence to stop recording
        self.MIN_RECORDING_CHUNKS = 10  # Minimum ~800ms of recording before allowing stop
        self.MAX_RECORDING_SECONDS = 8  # Maximum recording time

        # Models
        self.oww_model = None
        self.whisper_model = None

        # Audio
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.input_device_index = input_device_index  # None = default, or specific device index

        # Auto-select microphone if no device specified
        if self.input_device_index is None:
            self.input_device_index = self.find_microphone_device()

    def list_input_devices(self):
        """List all available input devices"""
        devices = []
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxInputChannels'],
                    'sample_rate': int(info['defaultSampleRate'])
                })
        return devices

    def find_microphone_device(self):
        """
        Find the best microphone device, excluding system audio/loopback.
        Returns device index or None for default.
        """
        devices = self.list_input_devices()

        # Keywords that indicate system audio (not a real microphone)
        system_audio_keywords = [
            'blackhole', 'soundflower', 'loopback', 'virtual',
            'aggregate', 'multi-output', 'system audio', 'what u hear',
            'stereo mix', 'wave out', 'output'
        ]

        # Keywords that indicate a real microphone
        microphone_keywords = [
            'microphone', 'mic', 'input', 'built-in', 'macbook',
            'headset', 'airpods', 'usb', 'external'
        ]

        print("\n=== Available Audio Input Devices ===")
        for dev in devices:
            print(f"  [{dev['index']}] {dev['name']} ({dev['channels']}ch, {dev['sample_rate']}Hz)")

        # Score each device
        best_device = None
        best_score = -100

        for dev in devices:
            name_lower = dev['name'].lower()
            score = 0

            # Penalize system audio devices heavily
            for keyword in system_audio_keywords:
                if keyword in name_lower:
                    score -= 50
                    break

            # Prefer devices with microphone keywords
            for keyword in microphone_keywords:
                if keyword in name_lower:
                    score += 10
                    break

            # Prefer built-in microphone on macOS
            if 'macbook' in name_lower or 'built-in' in name_lower:
                score += 5

            # Prefer devices that support our sample rate
            if dev['sample_rate'] == self.RATE or dev['sample_rate'] >= self.RATE:
                score += 2

            if score > best_score:
                best_score = score
                best_device = dev

        if best_device and best_score > 0:
            print(f"\n>>> Auto-selected microphone: [{best_device['index']}] {best_device['name']}")
            return best_device['index']
        else:
            print("\n>>> Using default input device")
            return None

    def set_input_device(self, device_index):
        """Change the input device (useful for runtime switching)"""
        self.input_device_index = device_index
        print(f"Input device set to index: {device_index}")

    def load_models(self):
        """Load AI models"""
        try:
            print("Loading wake word model...")
            self.oww_model = Model(
                wakeword_models=["hey_jarvis_v0.1"],
                inference_framework="onnx"
            )

            print("Loading speech recognition model...")
            self.whisper_model = whisper.load_model("base")
            print("DEBUG: Whisper model loaded")

            print("Models loaded successfully!")
            return True
        except Exception as e:
            print(f"Error loading models: {e}")
            return False

    def calculate_rms(self, audio_data):
        """Calculate RMS (root mean square) of audio for amplitude"""
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array**2))
        # Normalize to 0-1 range (adjust 3000 based on your mic sensitivity)
        normalized = min(1.0, rms / 3000)
        return normalized

    def start(self):
        """Start the voice assistant"""
        if self.is_running:
            return

        self.is_running = True
        print("Starting voice assistant...")

        # Start detection loop in background thread
        threading.Thread(target=self.detection_loop, daemon=True).start()

    def stop(self):
        """Stop the voice assistant"""
        self.is_running = False
        self.is_recording = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        print("Voice assistant stopped")

    def get_audio_rms(self, audio_data):
        """Calculate RMS of raw audio bytes"""
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        return np.sqrt(np.mean(audio_array**2))

    def is_silence(self, audio_data):
        """Check if audio chunk is silence"""
        return self.get_audio_rms(audio_data) < self.SILENCE_THRESHOLD

    def detection_loop(self):
        """Main detection loop"""
        # Load models
        if not self.load_models():
            return

        # Open audio stream with selected device
        try:
            stream_kwargs = {
                'format': self.FORMAT,
                'channels': self.CHANNELS,
                'rate': self.RATE,
                'input': True,
                'frames_per_buffer': self.CHUNK
            }

            # Use specific device if selected
            if self.input_device_index is not None:
                stream_kwargs['input_device_index'] = self.input_device_index
                device_info = self.audio.get_device_info_by_index(self.input_device_index)
                print(f"Using input device: {device_info['name']}")

            self.stream = self.audio.open(**stream_kwargs)

            print("Listening for wake word...")

        except Exception as e:
            print(f"Microphone error: {e}")
            return

        # VAD state
        silence_chunk_count = 0

        # Main loop
        while self.is_running:
            try:
                # Read audio
                audio_data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                # Calculate audio level for visualization
                audio_level = self.calculate_rms(audio_data)

                # If recording speech
                if self.is_recording:
                    self.recorded_frames.append(audio_data)

                    # Update volume indicator
                    self.overlay.signals.update_volume.emit(audio_level)

                    # Voice Activity Detection - check for silence
                    if self.is_silence(audio_data):
                        silence_chunk_count += 1
                    else:
                        silence_chunk_count = 0

                    # Check stopping conditions
                    recording_duration = len(self.recorded_frames)
                    max_chunks = self.MAX_RECORDING_SECONDS * self.RATE // self.CHUNK

                    # Stop if: (enough recording AND prolonged silence) OR max time reached
                    should_stop_silence = (
                        recording_duration >= self.MIN_RECORDING_CHUNKS and
                        silence_chunk_count >= self.MAX_SILENCE_CHUNKS
                    )
                    should_stop_max_time = recording_duration >= max_chunks

                    if should_stop_silence:
                        print(f"Stopped recording: silence detected after {recording_duration} chunks")
                        self.process_speech()
                    elif should_stop_max_time:
                        print(f"Stopped recording: max time reached")
                        self.process_speech()

                    continue

                # Maintain pre-roll buffer (circular buffer of recent audio)
                self.pre_roll_buffer.append(audio_data)
                if len(self.pre_roll_buffer) > self.PRE_ROLL_CHUNKS:
                    self.pre_roll_buffer.pop(0)

                # Check for wake word
                prediction = self.oww_model.predict(audio_array)

                for mdl_name, score in prediction.items():
                    if score > 0.5:
                        print(f"Wake word detected! (confidence: {score:.2f})")
                        print(f"DEBUG: Emitting show_overlay signal")

                        # Show overlay (no text initially)
                        self.overlay.signals.show_overlay.emit()
                        time.sleep(0.1)  # Give UI time to show

                        # Start recording with pre-roll buffer
                        self.is_recording = True
                        self.recorded_frames = list(self.pre_roll_buffer)  # Include pre-roll audio
                        self.pre_roll_buffer.clear()
                        silence_chunk_count = 0
                        break

            except Exception as e:
                print(f"Detection error: {e}")
                continue

    def transcribe_partial(self):
        """Transcribe partial audio for real-time feedback"""
        try:
            # Convert current frames to numpy array
            audio_data = b''.join(self.recorded_frames)
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # Quick transcription with lower quality for speed
            result = self.whisper_model.transcribe(
                audio_array,
                language="en",
                fp16=False,
                task="transcribe",
                temperature=0.0,
                best_of=1,
                beam_size=1,
                condition_on_previous_text=False
            )
            transcript = result["text"].strip()

            if transcript:
                self.overlay.signals.update_text.emit(transcript)

        except Exception as e:
            print(f"Partial transcription error: {e}")

    def trim_silence(self, frames):
        """Trim trailing silence from audio frames"""
        if not frames:
            return frames

        # Find last non-silent frame
        last_voice_idx = len(frames) - 1
        for i in range(len(frames) - 1, -1, -1):
            if not self.is_silence(frames[i]):
                last_voice_idx = i
                break

        # Keep a small buffer after last voice (2 chunks ~ 160ms)
        end_idx = min(last_voice_idx + 2, len(frames))
        return frames[:end_idx]

    def process_speech(self):
        """Transcribe recorded speech"""
        self.is_recording = False

        print("Processing speech...")
        self.overlay.signals.update_volume.emit(0)

        try:
            # Trim trailing silence for better transcription
            trimmed_frames = self.trim_silence(self.recorded_frames)

            if len(trimmed_frames) < 3:
                print("Audio too short, skipping transcription")
                self.overlay.signals.update_text.emit("(no speech detected)")
                return

            # Convert to numpy array
            audio_data = b''.join(trimmed_frames)
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            print(f"Transcribing {len(trimmed_frames)} chunks ({len(trimmed_frames) * self.CHUNK / self.RATE:.1f}s of audio)")

            # Final transcription with higher quality
            result = self.whisper_model.transcribe(
                audio_array,
                language="en",
                fp16=False,
                no_speech_threshold=0.6,  # Higher threshold to avoid hallucinations
                logprob_threshold=-1.0,   # Filter low-confidence outputs
                compression_ratio_threshold=2.4  # Filter repetitive hallucinations
            )
            transcript = result["text"].strip()

            if transcript:
                print(f"Final transcription: {transcript}")
                self.overlay.signals.update_text.emit(transcript)
            else:
                print("No speech detected")
                self.overlay.signals.update_text.emit("(no speech detected)")

        except Exception as e:
            print(f"Error: {e}")

        finally:
            self.recorded_frames = []
            # Overlay will auto-hide after delay

    def cleanup(self):
        """Cleanup resources"""
        self.stop()
        self.audio.terminate()


def start_http_server(port=8765):
    """Start a simple HTTP server in the background for serving orb.html"""
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


def list_audio_devices():
    """List all available input devices and exit"""
    audio = pyaudio.PyAudio()
    print("\n=== Available Audio Input Devices ===\n")

    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"  [{i}] {info['name']}")
            print(f"      Channels: {info['maxInputChannels']}, Sample Rate: {int(info['defaultSampleRate'])}Hz")

    audio.terminate()
    print("\nUsage: python voice_assistant.py --device <index>")
    print("       python voice_assistant.py  (auto-selects microphone)\n")


def parse_args():
    """Parse command line arguments"""
    import argparse
    parser = argparse.ArgumentParser(description='Voice Assistant with Wake Word Detection')
    parser.add_argument(
        '--list-devices', '-l',
        action='store_true',
        help='List available audio input devices and exit'
    )
    parser.add_argument(
        '--device', '-d',
        type=int,
        default=None,
        help='Audio input device index (use --list-devices to see available devices)'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # List devices and exit if requested
    if args.list_devices:
        list_audio_devices()
        return

    port = 8765

    # Start local HTTP server for orb.html
    server = start_http_server(port)

    app = QApplication(sys.argv)

    # Create overlay with HTTP port
    overlay = TransparentOverlay(http_port=port)

    # Create voice assistant with optional device selection
    assistant = VoiceAssistant(overlay, input_device_index=args.device)
    assistant.start()

    # Cleanup on exit
    app.aboutToQuit.connect(assistant.cleanup)

    try:
        sys.exit(app.exec_())
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
