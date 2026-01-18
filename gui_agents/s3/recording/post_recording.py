"""
Post-Recording Pipeline for Agent-S

Orchestrates the full workflow from recording to indexed skill:
1. Convert raw events to human-readable actions
2. Analyze recording with LLM (video/screenshots + events)
3. Parse analysis into structured Skill
4. Index skill into vector store

Usage:
    python post_recording.py /path/to/recording/
"""

import os
import sys
from pathlib import Path
from typing import Callable, Optional

# Add parent directory to path for imports
SCRIPT_DIR = Path(__file__).parent
AGENTS_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(AGENTS_ROOT))

from dotenv import load_dotenv
load_dotenv(AGENTS_ROOT / ".env")


class PostRecordingPipeline:
    """
    Pipeline for processing recordings into indexed skills.
    
    Orchestrates:
    1. Event conversion (events.jsonl → actions.txt)
    2. LLM analysis (video/screenshots + actions → log.md)
    3. Skill parsing (log.md → Skill object)
    4. Skill indexing (Skill → vector store)
    """
    
    def __init__(
        self,
        recording_path: Path,
        on_progress: Optional[Callable[[str, int], None]] = None,
        on_error: Optional[Callable[[str, Exception], None]] = None,
    ):
        """
        Initialize the pipeline.
        
        Args:
            recording_path: Path to the recording directory
            on_progress: Callback for progress updates (message, percent)
            on_error: Callback for errors (stage, exception)
        """
        self.recording_path = Path(recording_path)
        self.on_progress = on_progress or (lambda msg, pct: print(f"[{pct}%] {msg}"))
        self.on_error = on_error or (lambda stage, e: print(f"Error in {stage}: {e}"))
        
        # File paths
        self.events_file = self.recording_path / "events.jsonl"
        self.actions_file = self.recording_path / "actions.txt"
        self.log_file = self.recording_path / "log.md"
        self.video_file = self._find_video_file()
    
    def _find_video_file(self) -> Optional[Path]:
        """Find video file in recording directory."""
        video_extensions = [".mp4", ".mkv", ".webm", ".mov", ".avi"]
        for ext in video_extensions:
            for f in self.recording_path.glob(f"*{ext}"):
                return f
        return None
    
    def run(self) -> dict:
        """
        Run the full pipeline.
        
        Returns:
            Dict with results:
            - success: bool
            - recording_path: str
            - actions_file: str or None
            - log_file: str or None
            - skill_id: str or None
            - errors: list of error strings
        """
        results = {
            "success": False,
            "recording_path": str(self.recording_path),
            "actions_file": None,
            "log_file": None,
            "skill_id": None,
            "errors": [],
        }
        
        try:
            # Stage 1: Convert events to actions
            self.on_progress("Converting events to actions...", 10)
            actions_result = self._convert_events()
            if actions_result:
                results["actions_file"] = str(self.actions_file)
            else:
                results["errors"].append("Failed to convert events")
                return results
            
            # Stage 2: Analyze recording with LLM
            self.on_progress("Analyzing recording with AI...", 30)
            if self.video_file or (self.recording_path / "screenshots").exists():
                analyze_result = self._analyze_recording()
                if analyze_result:
                    results["log_file"] = str(self.log_file)
                else:
                    results["errors"].append("Failed to analyze recording")
            else:
                self.on_progress("No video/screenshots found, skipping analysis", 50)
                results["errors"].append("No video or screenshots found for analysis")
            
            # Stage 3: Index skill into store
            self.on_progress("Indexing skill...", 80)
            if self.log_file.exists():
                skill_id = self._index_skill()
                if skill_id:
                    results["skill_id"] = skill_id
                else:
                    results["errors"].append("Failed to index skill")
            else:
                results["errors"].append("No log.md file to index")
            
            # Complete
            self.on_progress("Complete!", 100)
            results["success"] = len(results["errors"]) == 0 or results["skill_id"] is not None
            
        except Exception as e:
            self.on_error("pipeline", e)
            results["errors"].append(str(e))
        
        return results
    
    def _convert_events(self) -> bool:
        """Convert events.jsonl to actions.txt."""
        if not self.events_file.exists():
            return False
        
        try:
            from gui_agents.s3.recording.convert_events import (
                load_events,
                convert_events,
                simplify_events,
            )
            
            events = load_events(self.events_file)
            events = simplify_events(events)
            actions = convert_events(events)
            
            output_text = "Actions\n" + "\n".join(actions)
            self.actions_file.write_text(output_text)
            
            return True
        except Exception as e:
            self.on_error("convert", e)
            return False
    
    def _analyze_recording(self) -> bool:
        """Analyze recording with LLM."""
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            self.on_error("analyze", ValueError("OPENROUTER_API_KEY not set"))
            return False
        
        try:
            from gui_agents.s3.recording.analyze import analyze_recording
            
            # Determine what to analyze (video or directory with screenshots)
            if self.video_file and self.video_file.exists():
                recording_path = self.video_file
            else:
                recording_path = self.recording_path
            
            actions_path = self.actions_file if self.actions_file.exists() else None
            recording_name = self.recording_path.name
            
            result = analyze_recording(
                recording_path=recording_path,
                actions_path=actions_path,
                api_key=api_key,
                recording_name=recording_name,
            )
            
            self.log_file.write_text(result, encoding="utf-8")
            return True
            
        except Exception as e:
            self.on_error("analyze", e)
            return False
    
    def _index_skill(self) -> Optional[str]:
        """Parse and index skill from log.md."""
        if not self.log_file.exists():
            return None
        
        try:
            from gui_agents.s3.skills import WorkflowParser, SkillStore
            
            parser = WorkflowParser()
            skill = parser.parse_file(self.log_file)
            
            if not skill:
                self.on_error("index", ValueError("Failed to parse log.md"))
                return None
            
            store = SkillStore()
            store.add_skill(skill)
            
            return skill.id
            
        except Exception as e:
            self.on_error("index", e)
            return None


def process_recording(
    recording_path: str | Path,
    on_progress: Optional[Callable[[str, int], None]] = None,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> dict:
    """
    Convenience function to process a recording.
    
    Args:
        recording_path: Path to recording directory
        on_progress: Progress callback
        on_error: Error callback
        
    Returns:
        Results dict from pipeline
    """
    pipeline = PostRecordingPipeline(
        recording_path=Path(recording_path),
        on_progress=on_progress,
        on_error=on_error,
    )
    return pipeline.run()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Post-process an Agent-S recording: convert, analyze, and index"
    )
    parser.add_argument(
        "recording_path",
        type=Path,
        help="Path to the recording directory",
    )
    parser.add_argument(
        "--skip-analyze",
        action="store_true",
        help="Skip the AI analysis step",
    )
    
    args = parser.parse_args()
    
    if not args.recording_path.exists():
        print(f"Error: Recording path not found: {args.recording_path}")
        return 1
    
    def progress_callback(msg: str, pct: int):
        print(f"[{pct:3d}%] {msg}")
    
    def error_callback(stage: str, e: Exception):
        print(f"ERROR in {stage}: {e}")
    
    pipeline = PostRecordingPipeline(
        recording_path=args.recording_path,
        on_progress=progress_callback,
        on_error=error_callback,
    )
    
    if args.skip_analyze:
        # Skip analysis by mocking the method
        pipeline._analyze_recording = lambda: True
    
    results = pipeline.run()
    
    print("\n" + "=" * 50)
    print("RESULTS")
    print("=" * 50)
    print(f"Success: {results['success']}")
    print(f"Recording: {results['recording_path']}")
    print(f"Actions: {results['actions_file']}")
    print(f"Log: {results['log_file']}")
    print(f"Skill ID: {results['skill_id']}")
    
    if results["errors"]:
        print(f"Errors: {results['errors']}")
    
    return 0 if results["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
