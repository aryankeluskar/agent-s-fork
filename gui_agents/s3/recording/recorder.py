"""
Screen Recording with Event Capture

Records user interactions (mouse clicks, keyboard presses, scrolls) alongside
screen captures for later workflow analysis and skill extraction.

Supports TWO capture modes (no OBS required):

1. EVENT-TRIGGERED SCREENSHOTS (default, lightweight):
   - Captures on clicks, hotkeys, scroll stops, idle periods
   - Lower disk usage, captures what matters

2. FULL VIDEO RECORDING (optional):
   - Uses mss + OpenCV to record actual video
   - 15-30 FPS depending on resolution
   - Requires: pip install opencv-python

Both modes capture events to events.jsonl for action analysis.
"""

import json
import os
import time
import threading
import platform
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from typing import Optional, Callable, Set, Literal

from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode


# Modifier keys that indicate a hotkey combo
MODIFIER_KEYS = {
    'cmd', 'cmd_l', 'cmd_r',
    'ctrl', 'ctrl_l', 'ctrl_r', 
    'alt', 'alt_l', 'alt_r', 'alt_gr',
    'shift', 'shift_l', 'shift_r',
}

# Recording modes
RecordingMode = Literal["screenshots", "video"]


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


class VideoWriter:
    """
    Handles video recording using mss + OpenCV.
    No OBS required - pure Python solution.
    """
    
    def __init__(
        self,
        output_path: Path,
        fps: int = 15,
        scale: float = 0.5,  # Scale down for smaller files
    ):
        """
        Initialize video writer.
        
        Args:
            output_path: Path to save video file (.mp4)
            fps: Target frames per second (15-30 recommended)
            scale: Scale factor (0.5 = half resolution, smaller files)
        """
        self.output_path = output_path
        self.target_fps = fps
        self.scale = scale
        
        self._is_recording = False
        self._is_paused = False
        self._thread: Optional[threading.Thread] = None
        self._writer = None
        self._frame_count = 0
        self._start_time: Optional[float] = None
        
    def start(self):
        """Start video recording in background thread."""
        if self._is_recording:
            return
        
        self._is_recording = True
        self._is_paused = False
        self._frame_count = 0
        self._start_time = time.perf_counter()
        
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
    
    def pause(self):
        """Pause recording."""
        self._is_paused = True
    
    def resume(self):
        """Resume recording."""
        self._is_paused = False
    
    def stop(self) -> dict:
        """
        Stop recording and finalize video file.
        
        Returns:
            Dict with recording stats
        """
        self._is_recording = False
        
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        
        if self._writer:
            self._writer.release()
            self._writer = None
        
        duration = time.perf_counter() - self._start_time if self._start_time else 0
        actual_fps = self._frame_count / duration if duration > 0 else 0
        
        return {
            "frames": self._frame_count,
            "duration_seconds": duration,
            "actual_fps": actual_fps,
            "video_path": str(self.output_path),
        }
    
    def _record_loop(self):
        """Background thread that captures frames and writes to video."""
        try:
            import cv2
            import mss
            import numpy as np
        except ImportError as e:
            print(f"Video recording requires: pip install opencv-python mss numpy")
            print(f"Missing: {e}")
            self._is_recording = False
            return
        
        frame_interval = 1.0 / self.target_fps
        
        with mss.mss() as sct:
            # Get monitor info
            monitor = sct.monitors[1]  # Primary monitor
            width = int(monitor["width"] * self.scale)
            height = int(monitor["height"] * self.scale)
            
            # Initialize video writer
            # Use mp4v codec for broad compatibility
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self._writer = cv2.VideoWriter(
                str(self.output_path),
                fourcc,
                self.target_fps,
                (width, height)
            )
            
            if not self._writer.isOpened():
                print(f"Failed to open video writer at {self.output_path}")
                self._is_recording = False
                return
            
            print(f"Video recording started: {width}x{height} @ {self.target_fps}fps")
            
            last_frame_time = time.perf_counter()
            
            while self._is_recording:
                if self._is_paused:
                    time.sleep(0.1)
                    continue
                
                current_time = time.perf_counter()
                elapsed = current_time - last_frame_time
                
                if elapsed >= frame_interval:
                    try:
                        # Capture screen
                        screenshot = sct.grab(monitor)
                        
                        # Convert to numpy array
                        frame = np.array(screenshot)
                        
                        # Convert BGRA to BGR (OpenCV format)
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        
                        # Resize if scaling
                        if self.scale != 1.0:
                            frame = cv2.resize(frame, (width, height))
                        
                        # Write frame
                        self._writer.write(frame)
                        self._frame_count += 1
                        
                        last_frame_time = current_time
                        
                    except Exception as e:
                        print(f"Frame capture error: {e}")
                
                # Small sleep to prevent CPU hogging
                sleep_time = max(0.001, frame_interval - (time.perf_counter() - current_time))
                time.sleep(sleep_time)


class Recorder:
    """
    Records user interactions (mouse/keyboard events) to events.jsonl
    with visual capture (video or screenshots).
    
    Two modes available:
    
    1. "video" (default) - Full screen recording:
       - Continuous video using mss + OpenCV (no OBS needed)
       - 15-30 fps depending on settings
       - Complete visual record for LLM analysis
       
    2. "screenshots" - Event-triggered screenshots:
       - Captures on clicks, hotkeys, scroll stops, idle periods
       - Lower disk usage, captures key moments only
    
    Usage:
        # Video mode (default)
        recorder = Recorder()
        
        # Screenshot mode
        recorder = Recorder(mode="screenshots")
        
        recorder.start()
        # ... user performs actions ...
        recorder.stop()
    """
    
    def __init__(
        self, 
        recording_name: Optional[str] = None,
        mode: RecordingMode = "video",
        natural_scrolling: bool = True,
        # Screenshot mode options
        capture_screenshots: bool = True,
        screenshot_debounce: float = 0.3,
        idle_screenshot_interval: float = 3.0,
        # Video mode options
        video_fps: int = 15,
        video_scale: float = 0.5,  # 0.5 = half resolution
        on_recording_stopped: Optional[Callable] = None,
    ):
        """
        Initialize the recorder.
        
        Args:
            recording_name: Optional name for the recording folder
            mode: "video" (default) or "screenshots"
            natural_scrolling: Whether to use natural scrolling direction
            capture_screenshots: Whether to capture event-triggered screenshots
            screenshot_debounce: Minimum seconds between screenshots
            idle_screenshot_interval: Capture screenshot if no action for this long
            video_fps: Frames per second for video mode (15-30 recommended)
            video_scale: Scale factor for video (0.5 = smaller files)
            on_recording_stopped: Callback when recording stops
        """
        self.recording_name = recording_name
        self.mode = mode
        self.natural_scrolling = natural_scrolling
        self.capture_screenshots = capture_screenshots if mode == "screenshots" else False
        self.screenshot_debounce = screenshot_debounce
        self.idle_screenshot_interval = idle_screenshot_interval
        self.video_fps = video_fps
        self.video_scale = video_scale
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
        self._idle_screenshot_thread: Optional[threading.Thread] = None
        
        # Screenshot state (for screenshots mode)
        self._screenshot_count = 0
        self._last_screenshot_time: float = 0
        self._last_action_time: float = 0
        self._screenshot_lock = threading.Lock()
        self._screenshots_dir: Optional[Path] = None
        self._sct = None  # mss screenshot instance
        
        # Video state (for video mode)
        self._video_writer: Optional[VideoWriter] = None
        
        # Keyboard state for hotkey detection
        self._pressed_modifiers: Set[str] = set()
        self._last_scroll_time: float = 0
        self._scroll_screenshot_pending: bool = False

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

    def _capture_screenshot(self, trigger: str = "manual") -> Optional[str]:
        """
        Capture a screenshot if enough time has passed since the last one.
        
        Args:
            trigger: What triggered this screenshot (click, hotkey, scroll, idle)
            
        Returns:
            Filename of captured screenshot, or None if debounced
        """
        if not self.capture_screenshots or not self._is_recording or self._is_paused:
            return None
        
        current_time = time.perf_counter()
        
        with self._screenshot_lock:
            # Debounce - skip if too recent (except for clicks which are important)
            time_since_last = current_time - self._last_screenshot_time
            if time_since_last < self.screenshot_debounce and trigger != "click":
                return None
            
            try:
                if self._sct is None:
                    import mss
                    self._sct = mss.mss()
                
                # Capture primary monitor
                monitor = self._sct.monitors[1]
                screenshot = self._sct.grab(monitor)
                
                # Save screenshot
                self._screenshot_count += 1
                filename = f"frame_{self._screenshot_count:05d}_{trigger}.png"
                filepath = self._screenshots_dir / filename
                
                import mss.tools
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filepath))
                
                self._last_screenshot_time = current_time
                
                # Log screenshot event
                self.event_queue.put({
                    "time_stamp": self._get_relative_time(),
                    "action": "screenshot",
                    "filename": filename,
                    "trigger": trigger
                }, block=False)
                
                return filename
                
            except Exception as e:
                print(f"Screenshot error: {e}")
                return None

    def _update_action_time(self):
        """Update the last action time for idle detection."""
        self._last_action_time = time.perf_counter()

    # Mouse event handlers
    def _on_move(self, x: int, y: int):
        """Handle mouse move events (no screenshot - too frequent)."""
        if self._is_recording and not self._is_paused:
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "move",
                "x": x,
                "y": y
            }, block=False)
            # Don't update action time for moves - they're continuous
            # and would prevent idle screenshots

    def _on_click(self, x: int, y: int, button, pressed: bool):
        """Handle mouse click events - captures screenshot BEFORE click."""
        if self._is_recording and not self._is_paused:
            # Capture screenshot BEFORE the click (on press, not release)
            if pressed:
                self._capture_screenshot("click")
            
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "click",
                "x": x,
                "y": y,
                "button": button.name,
                "pressed": pressed
            }, block=False)
            
            self._update_action_time()

    def _on_scroll(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse scroll events - captures screenshot after scroll stops."""
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
            
            # Mark that we should capture after scroll stops
            self._last_scroll_time = time.perf_counter()
            self._scroll_screenshot_pending = True
            self._update_action_time()

    # Keyboard event handlers
    def _on_press(self, key):
        """Handle keyboard press events - captures screenshot on hotkey combos."""
        if self._is_recording and not self._is_paused:
            key_name = key.char if isinstance(key, KeyCode) and key.char else (key.name if hasattr(key, 'name') else str(key))
            
            # Track modifier keys
            if key_name and key_name.lower() in MODIFIER_KEYS:
                self._pressed_modifiers.add(key_name.lower())
            
            # Capture screenshot on hotkey (modifier + non-modifier key)
            elif self._pressed_modifiers and key_name:
                # This is a hotkey combo like Cmd+C, Ctrl+V, etc.
                self._capture_screenshot("hotkey")
            
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "press",
                "key": key_name
            }, block=False)
            
            self._update_action_time()

    def _on_release(self, key):
        """Handle keyboard release events."""
        if self._is_recording and not self._is_paused:
            key_name = key.char if isinstance(key, KeyCode) and key.char else (key.name if hasattr(key, 'name') else str(key))
            
            # Remove modifier from tracking
            if key_name and key_name.lower() in MODIFIER_KEYS:
                self._pressed_modifiers.discard(key_name.lower())
            
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

    def _idle_screenshot_loop(self):
        """
        Background thread to handle:
        1. Idle screenshots (no activity for a while)
        2. Scroll-stop screenshots (after scrolling settles)
        """
        SCROLL_SETTLE_TIME = 0.4  # Time after last scroll to capture
        
        while self._is_recording:
            if not self._is_paused:
                current_time = time.perf_counter()
                
                # Check for scroll stop
                if self._scroll_screenshot_pending:
                    time_since_scroll = current_time - self._last_scroll_time
                    if time_since_scroll >= SCROLL_SETTLE_TIME:
                        self._capture_screenshot("scroll")
                        self._scroll_screenshot_pending = False
                
                # Check for idle (no activity for a while)
                time_since_action = current_time - self._last_action_time
                time_since_screenshot = current_time - self._last_screenshot_time
                
                if (time_since_action >= self.idle_screenshot_interval and 
                    time_since_screenshot >= self.idle_screenshot_interval):
                    self._capture_screenshot("idle")
            
            time.sleep(0.1)  # Check frequently for scroll stops

    def start(self):
        """Start recording events with visual capture (screenshots or video)."""
        if self._is_recording:
            print("Already recording")
            return
        
        # Initialize recording directory
        self.recording_path = self._get_recording_path()
        
        # Setup visual capture based on mode
        if self.mode == "video":
            # Video mode - full screen recording
            video_path = self.recording_path / "recording.mp4"
            self._video_writer = VideoWriter(
                output_path=video_path,
                fps=self.video_fps,
                scale=self.video_scale,
            )
            self._video_writer.start()
            
        elif self.capture_screenshots:
            # Screenshot mode - event-triggered captures
            self._screenshots_dir = self.recording_path / "screenshots"
            self._screenshots_dir.mkdir(exist_ok=True)
            
            try:
                import mss
                self._sct = mss.mss()
            except ImportError:
                print("Warning: mss not installed, screenshots disabled")
                self.capture_screenshots = False
        
        # Open events file
        events_file_path = self.recording_path / "events.jsonl"
        self.events_file = open(events_file_path, "a")
        
        # Save metadata
        metadata = {
            "recording_name": self.recording_name,
            "start_time": datetime.now().isoformat(),
            "platform": platform.system(),
            "natural_scrolling": self.natural_scrolling,
            "capture_mode": self.mode,
            "video_fps": self.video_fps if self.mode == "video" else None,
            "video_scale": self.video_scale if self.mode == "video" else None,
        }
        metadata_path = self.recording_path / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))
        
        # Initialize timing state
        current_time = time.perf_counter()
        self._start_time = current_time
        self._last_screenshot_time = current_time
        self._last_action_time = current_time
        self._last_scroll_time = 0
        self._scroll_screenshot_pending = False
        self._pressed_modifiers.clear()
        
        self._is_recording = True
        self._is_paused = False
        self._screenshot_count = 0
        
        # Capture initial screenshot (screenshot mode only)
        if self.mode == "screenshots" and self.capture_screenshots:
            self._capture_screenshot("start")
        
        # Start event writer thread
        self._event_writer_thread = threading.Thread(
            target=self._event_writer_loop,
            daemon=True
        )
        self._event_writer_thread.start()
        
        # Start idle/scroll screenshot thread if in screenshot mode
        if self.mode == "screenshots" and self.capture_screenshots:
            self._idle_screenshot_thread = threading.Thread(
                target=self._idle_screenshot_loop,
                daemon=True
            )
            self._idle_screenshot_thread.start()
        
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
        if self.mode == "video":
            print(f"Mode: VIDEO ({self.video_fps}fps, {self.video_scale:.0%} scale)")
        else:
            print(f"Mode: SCREENSHOTS (event-triggered)")

    def pause(self):
        """Pause recording."""
        if self._is_recording and not self._is_paused:
            self._is_paused = True
            
            # Pause video writer if in video mode
            if self._video_writer:
                self._video_writer.pause()
            
            self.event_queue.put({
                "time_stamp": self._get_relative_time(),
                "action": "pause"
            }, block=False)
            print("Recording paused")

    def resume(self):
        """Resume recording."""
        if self._is_recording and self._is_paused:
            self._is_paused = False
            
            # Resume video writer if in video mode
            if self._video_writer:
                self._video_writer.resume()
            
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
        
        # Capture final screenshot (screenshot mode only)
        if self.mode == "screenshots" and self.capture_screenshots:
            self._capture_screenshot("end")
        
        self._is_recording = False
        
        # Stop video writer if in video mode
        video_stats = None
        if self._video_writer:
            video_stats = self._video_writer.stop()
            self._video_writer = None
        
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
        
        if self._idle_screenshot_thread:
            self._idle_screenshot_thread.join(timeout=2.0)
            self._idle_screenshot_thread = None
        
        # Close events file
        if self.events_file:
            self.events_file.close()
            self.events_file = None
        
        # Close mss
        if self._sct:
            self._sct.close()
            self._sct = None
        
        # Update metadata with end time
        metadata_path = self.recording_path / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            metadata["end_time"] = datetime.now().isoformat()
            metadata["duration_seconds"] = self._get_relative_time()
            
            if self.mode == "video" and video_stats:
                metadata["video_frames"] = video_stats["frames"]
                metadata["video_actual_fps"] = video_stats["actual_fps"]
                metadata["video_path"] = video_stats["video_path"]
            else:
                metadata["screenshot_count"] = self._screenshot_count
            
            metadata_path.write_text(json.dumps(metadata, indent=2))
        
        print(f"Recording stopped: {self.recording_path}")
        if self.mode == "video" and video_stats:
            print(f"Video: {video_stats['frames']} frames, {video_stats['actual_fps']:.1f} fps")
        else:
            print(f"Screenshots: {self._screenshot_count} event-triggered captures")
        
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
