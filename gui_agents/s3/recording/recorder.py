"""
Screen Recording with Event Capture

Records user interactions (mouse clicks, keyboard presses, scrolls) alongside
screen video for later workflow analysis and skill extraction.
"""

import json
import os
import time
import threading
import platform
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from typing import Optional, Callable

from pynput import keyboard, mouse
from pynput.keyboard import KeyCode


def get_recordings_dir() -> Path:
    """Get the default recordings directory."""
    if platform.system() == "Darwin":
        recordings_dir = Path.home() / "Documents" / "AgentS_Recordings"
    elif platform.system() == "Windows":
        recordings_dir = Path.home() / "Documents" / "AgentS_Recordings"
    else:
        recordings_dir = Path.home() / "AgentS_Recordings"
    
    recordings_dir.mkdir(parents=True, exist_ok=True)
    return recordings_dir


def get_latest_recording() -> Optional[Path]:
    """Get the most recent recording directory."""
    recordings_dir = get_recordings_dir()
    recordings = sorted(
        [d for d in recordings_dir.iterdir() if d.is_dir()],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    return recordings[0] if recordings else None


class Recorder:
    """
    Records user interactions (mouse/keyboard events) to events.jsonl.
    Can optionally integrate with screen recording via mss for screenshots.
    
    Usage:
        recorder = Recorder()
        recorder.start()
        # ... user performs actions ...
        recorder.stop()
        print(f"Recording saved to: {recorder.recording_path}")
    """
    
    def __init__(
        self, 
        recording_name: Optional[str] = None,
        natural_scrolling: bool = True,
        capture_screenshots: bool = True,
        screenshot_interval: float = 1.0,
        on_recording_stopped: Optional[Callable] = None,
    ):
        """
        Initialize the recorder.
        
        Args:
            recording_name: Optional name for the recording folder
            natural_scrolling: Whether to use natural scrolling direction (macOS default)
            capture_screenshots: Whether to capture periodic screenshots
            screenshot_interval: Interval between screenshot captures in seconds
            on_recording_stopped: Callback when recording stops
        """
        self.recording_name = recording_name
        self.natural_scrolling = natural_scrolling
        self.capture_screenshots = capture_screenshots
        self.screenshot_interval = screenshot_interval
        self.on_recording_stopped = on_recording_stopped
        
        # State
        self._is_recording = False
        self._is_paused = False
        self._start_time: Optional[float] = None
        
        # Recording path
        self.recording_path: Optional[Path] = None
        
        # Event queue and file
        self.event_queue: Queue = Queue()
        self.events_file = None
        
        # Listeners
        self.mouse_listener: Optional[mouse.Listener] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None
        
        # Threads
        self._event_writer_thread: Optional[threading.Thread] = None
        self._screenshot_thread: Optional[threading.Thread] = None
        
        # Screenshot counter
        self._screenshot_count = 0

    def _get_recording_path(self) -> Path:
        """Generate a unique recording directory path."""
        recordings_dir = get_recordings_dir()
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        if self.recording_name:
            folder_name = f"{timestamp}_{self.recording_name}"
        else:
            folder_name = f"recording-{timestamp}"
        
        recording_path = recordings_dir / folder_name
        recording_path.mkdir(parents=True, exist_ok=True)
        
        return recording_path

    def _get_relative_time(self) -> float:
        """Get time since recording started."""
        if self._start_time is None:
            return 0.0
        return time.perf_counter() - self._start_time

    # Mouse event handlers
    def _on_move(self, x: int, y: int):
        """Handle mouse move events."""
        if self._is_recording and not self._is_paused:
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "move",
                "x": x,
                "y": y
            }, block=False)

    def _on_click(self, x: int, y: int, button, pressed: bool):
        """Handle mouse click events."""
        if self._is_recording and not self._is_paused:
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "click",
                "x": x,
                "y": y,
                "button": button.name,
                "pressed": pressed
            }, block=False)

    def _on_scroll(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse scroll events."""
        if self._is_recording and not self._is_paused:
            # Apply natural scrolling if enabled
            if not self.natural_scrolling:
                dy = -dy
                dx = -dx
            
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "scroll",
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy
            }, block=False)

    # Keyboard event handlers
    def _on_press(self, key):
        """Handle keyboard press events."""
        if self._is_recording and not self._is_paused:
            key_name = key.char if isinstance(key, KeyCode) else key.name
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "press",
                "key": key_name
            }, block=False)

    def _on_release(self, key):
        """Handle keyboard release events."""
        if self._is_recording and not self._is_paused:
            key_name = key.char if isinstance(key, KeyCode) else key.name
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "release",
                "key": key_name
            }, block=False)

    def _event_writer_loop(self):
        """Background thread to write events to file."""
        while self._is_recording:
            try:
                event = self.event_queue.get(timeout=0.1)
                if self.events_file and not self.events_file.closed:
                    self.events_file.write(json.dumps(event) + "\n")
                    self.events_file.flush()
            except Empty:
                continue
            except Exception as e:
                print(f"Error writing event: {e}")

    def _screenshot_loop(self):
        """Background thread to capture periodic screenshots."""
        try:
            import mss
        except ImportError:
            print("Warning: mss not installed, screenshots disabled")
            return
        
        screenshots_dir = self.recording_path / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        
        with mss.mss() as sct:
            while self._is_recording:
                if not self._is_paused:
                    try:
                        # Capture primary monitor
                        monitor = sct.monitors[1]
                        screenshot = sct.grab(monitor)
                        
                        # Save screenshot
                        self._screenshot_count += 1
                        filename = screenshots_dir / f"frame_{self._screenshot_count:05d}.png"
                        mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filename))
                        
                        # Log screenshot event
                        self.event_queue.put({
                            "time_stamp": self._get_relative_time(),
                            "action": "screenshot",
                            "filename": str(filename.name)
                        }, block=False)
                        
                    except Exception as e:
                        print(f"Screenshot error: {e}")
                
                time.sleep(self.screenshot_interval)

    def start(self):
        """Start recording events and optionally screenshots."""
        if self._is_recording:
            print("Already recording")
            return
        
        # Initialize recording directory
        self.recording_path = self._get_recording_path()
        
        # Open events file
        events_file_path = self.recording_path / "events.jsonl"
        self.events_file = open(events_file_path, "a")
        
        # Save metadata
        metadata = {
            "recording_name": self.recording_name,
            "start_time": datetime.now().isoformat(),
            "platform": platform.system(),
            "natural_scrolling": self.natural_scrolling,
            "capture_screenshots": self.capture_screenshots,
        }
        metadata_path = self.recording_path / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))
        
        # Start recording
        self._start_time = time.perf_counter()
        self._is_recording = True
        self._is_paused = False
        self._screenshot_count = 0
        
        # Start event writer thread
        self._event_writer_thread = threading.Thread(
            target=self._event_writer_loop,
            daemon=True
        )
        self._event_writer_thread.start()
        
        # Start screenshot thread if enabled
        if self.capture_screenshots:
            self._screenshot_thread = threading.Thread(
                target=self._screenshot_loop,
                daemon=True
            )
            self._screenshot_thread.start()
        
        # Start mouse listener
        self.mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll
        )
        self.mouse_listener.start()
        
        # Start keyboard listener
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.keyboard_listener.start()
        
        print(f"Recording started: {self.recording_path}")

    def pause(self):
        """Pause recording."""
        if self._is_recording and not self._is_paused:
            self._is_paused = True
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "pause"
            }, block=False)
            print("Recording paused")

    def resume(self):
        """Resume recording."""
        if self._is_recording and self._is_paused:
            self._is_paused = False
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "resume"
            }, block=False)
            print("Recording resumed")

    def stop(self) -> Path:
        """
        Stop recording and return the recording path.
        
        Returns:
            Path to the recording directory
        """
        if not self._is_recording:
            print("Not recording")
            return self.recording_path
        
        self._is_recording = False
        
        # Stop listeners
        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener = None
        
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
        
        # Wait for threads to finish
        if self._event_writer_thread:
            self._event_writer_thread.join(timeout=2.0)
            self._event_writer_thread = None
        
        if self._screenshot_thread:
            self._screenshot_thread.join(timeout=2.0)
            self._screenshot_thread = None
        
        # Close events file
        if self.events_file:
            self.events_file.close()
            self.events_file = None
        
        # Update metadata with end time
        metadata_path = self.recording_path / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            metadata["end_time"] = datetime.now().isoformat()
            metadata["duration_seconds"] = self._get_relative_time()
            metadata["screenshot_count"] = self._screenshot_count
            metadata_path.write_text(json.dumps(metadata, indent=2))
        
        print(f"Recording stopped: {self.recording_path}")
        
        # Call callback if provided
        if self.on_recording_stopped:
            self.on_recording_stopped(self.recording_path)
        
        return self.recording_path

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording

    @property
    def is_paused(self) -> bool:
        """Check if recording is paused."""
        return self._is_paused
