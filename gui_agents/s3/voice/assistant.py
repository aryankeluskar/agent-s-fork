"""
Voice Assistant

Main voice assistant class with:
- Wake word detection (openwakeword)
- Voice activity detection (VAD)
- Integration with Wispr Flow transcription
- Transparent overlay UI
"""

import threading
import time
from typing import List, Optional

import numpy as np
import pyaudio
from openwakeword.model import Model

from .transcriber import WisprTranscriber
from .overlay import TransparentOverlay


class VoiceAssistant:
    """Voice assistant with wake word detection and transcription."""

    def __init__(
        self, 
        overlay: TransparentOverlay, 
        input_device_index: Optional[int] = None
    ):
        self.overlay = overlay

        # State
        self.is_running = False
        self.is_recording = False
        self.recorded_frames: List[bytes] = []

        # Audio configuration
        self.CHUNK = 1280  # 80ms at 16kHz
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000

        # Pre-roll buffer
        self.pre_roll_buffer: List[bytes] = []
        self.PRE_ROLL_CHUNKS = 5  # ~400ms

        # VAD settings
        self.SILENCE_THRESHOLD = 400
        self.MAX_SILENCE_CHUNKS = 18  # ~1.4s
        self.MIN_RECORDING_CHUNKS = 10  # ~800ms
        self.MAX_RECORDING_SECONDS = 8

        # Models
        self.oww_model = None
        self.transcriber = WisprTranscriber()

        # Audio
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.input_device_index = input_device_index

        # Auto-select microphone if not specified
        if self.input_device_index is None:
            self.input_device_index = self.find_microphone_device()

    def list_input_devices(self) -> List[dict]:
        """List all available input devices."""
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

    def find_microphone_device(self) -> Optional[int]:
        """Find the best microphone device, excluding system audio."""
        devices = self.list_input_devices()

        # Keywords for system audio (not a real microphone)
        system_audio_keywords = [
            'blackhole', 'soundflower', 'loopback', 'virtual',
            'aggregate', 'multi-output', 'system audio', 'what u hear',
            'stereo mix', 'wave out', 'output'
        ]

        # Keywords for real microphones
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

            for keyword in system_audio_keywords:
                if keyword in name_lower:
                    score -= 50
                    break

            for keyword in microphone_keywords:
                if keyword in name_lower:
                    score += 10
                    break

            if 'macbook' in name_lower or 'built-in' in name_lower:
                score += 5

            if dev['sample_rate'] >= self.RATE:
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

    def set_input_device(self, device_index: int):
        """Change the input device."""
        self.input_device_index = device_index
        print(f"Input device set to index: {device_index}")

    def load_models(self) -> bool:
        """Load AI models (wake word only)."""
        try:
            print("Loading wake word model...")
            self.oww_model = Model(
                wakeword_models=["hey_jarvis_v0.1"],
                inference_framework="onnx"
            )
            print("Transcription: Using Wispr Flow API")
            print("Models loaded successfully!")
            return True
        except Exception as e:
            print(f"Error loading models: {e}")
            return False

    def calculate_rms(self, audio_data: bytes) -> float:
        """Calculate RMS of audio for amplitude."""
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array**2))
        return min(1.0, rms / 3000)

    def is_silence(self, audio_data: bytes) -> bool:
        """Check if audio chunk is silence."""
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array**2))
        return rms < self.SILENCE_THRESHOLD

    def start(self):
        """Start the voice assistant."""
        if self.is_running:
            return

        self.is_running = True
        print("Starting voice assistant...")
        threading.Thread(target=self.detection_loop, daemon=True).start()

    def stop(self):
        """Stop the voice assistant."""
        self.is_running = False
        self.is_recording = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        print("Voice assistant stopped")

    def detection_loop(self):
        """Main detection loop."""
        if not self.load_models():
            return

        try:
            stream_kwargs = {
                'format': self.FORMAT,
                'channels': self.CHANNELS,
                'rate': self.RATE,
                'input': True,
                'frames_per_buffer': self.CHUNK
            }

            if self.input_device_index is not None:
                stream_kwargs['input_device_index'] = self.input_device_index
                device_info = self.audio.get_device_info_by_index(self.input_device_index)
                print(f"Using input device: {device_info['name']}")

            self.stream = self.audio.open(**stream_kwargs)
            print("Listening for wake word...")

        except Exception as e:
            print(f"Microphone error: {e}")
            return

        silence_chunk_count = 0

        while self.is_running:
            try:
                audio_data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                audio_level = self.calculate_rms(audio_data)

                if self.is_recording:
                    self.recorded_frames.append(audio_data)
                    self.overlay.signals.update_volume.emit(audio_level)

                    if self.is_silence(audio_data):
                        silence_chunk_count += 1
                    else:
                        silence_chunk_count = 0

                    recording_duration = len(self.recorded_frames)
                    max_chunks = self.MAX_RECORDING_SECONDS * self.RATE // self.CHUNK

                    should_stop_silence = (
                        recording_duration >= self.MIN_RECORDING_CHUNKS and
                        silence_chunk_count >= self.MAX_SILENCE_CHUNKS
                    )
                    should_stop_max_time = recording_duration >= max_chunks

                    if should_stop_silence:
                        print(f"Stopped recording: silence detected")
                        self.process_speech()
                    elif should_stop_max_time:
                        print(f"Stopped recording: max time reached")
                        self.process_speech()

                    continue

                # Maintain pre-roll buffer
                self.pre_roll_buffer.append(audio_data)
                if len(self.pre_roll_buffer) > self.PRE_ROLL_CHUNKS:
                    self.pre_roll_buffer.pop(0)

                # Check for wake word
                prediction = self.oww_model.predict(audio_array)

                for mdl_name, score in prediction.items():
                    if score > 0.5:
                        print(f"Wake word detected! (confidence: {score:.2f})")
                        self.overlay.signals.show_overlay.emit()
                        time.sleep(0.1)

                        self.is_recording = True
                        self.recorded_frames = list(self.pre_roll_buffer)
                        self.pre_roll_buffer.clear()
                        silence_chunk_count = 0
                        break

            except Exception as e:
                print(f"Detection error: {e}")
                continue

    def on_partial_transcription(self, text: str):
        """Callback for partial transcription updates."""
        if text:
            self.overlay.signals.update_text.emit(text + "...")

    def trim_silence(self, frames: List[bytes]) -> List[bytes]:
        """Trim trailing silence from audio frames."""
        if not frames:
            return frames

        last_voice_idx = len(frames) - 1
        for i in range(len(frames) - 1, -1, -1):
            if not self.is_silence(frames[i]):
                last_voice_idx = i
                break

        end_idx = min(last_voice_idx + 2, len(frames))
        return frames[:end_idx]

    def process_speech(self):
        """Transcribe recorded speech."""
        self.is_recording = False

        print("Processing speech...")
        self.overlay.signals.update_volume.emit(0)
        self.overlay.signals.update_text.emit("Transcribing...")

        try:
            trimmed_frames = self.trim_silence(self.recorded_frames)

            if len(trimmed_frames) < 3:
                print("Audio too short, skipping transcription")
                self.overlay.signals.update_text.emit("(no speech detected)")
                return

            audio_duration = len(trimmed_frames) * self.CHUNK / self.RATE
            print(f"Transcribing {len(trimmed_frames)} chunks ({audio_duration:.1f}s)")

            transcript = self.transcriber.transcribe_sync(
                trimmed_frames,
                on_partial=self.on_partial_transcription
            )

            if transcript:
                print(f"Final transcription: {transcript}")
                self.overlay.signals.update_text.emit(transcript)
            else:
                print("No speech detected")
                self.overlay.signals.update_text.emit("(no speech detected)")

        except Exception as e:
            print(f"Transcription error: {e}")
            self.overlay.signals.update_text.emit("(transcription failed)")

        finally:
            self.recorded_frames = []

    def cleanup(self):
        """Cleanup resources."""
        self.stop()
        self.audio.terminate()
