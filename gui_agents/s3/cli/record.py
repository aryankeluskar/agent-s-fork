"""
Agent-S Record Command

Record workflows for skill learning with automatic analysis.
When recording stops, automatically:
1. Converts events to human-readable actions
2. Analyzes with LLM
3. Parses into structured Skill
4. Indexes into vector store
"""

import json
import sys
import time
from pathlib import Path


def _auto_process_recording(recording_path: Path):
    """
    Automatically triggered when recording stops.
    Runs the full post-recording pipeline.
    """
    print("\n" + "=" * 60)
    print("🔄 Processing recording...")
    print("=" * 60)
    
    from gui_agents.s3.recording import process_recording
    
    def progress_callback(msg: str, pct: int):
        print(f"[{pct:3d}%] {msg}")
    
    def error_callback(stage: str, e: Exception):
        print(f"⚠️  Error in {stage}: {e}")
    
    results = process_recording(
        recording_path,
        on_progress=progress_callback,
        on_error=error_callback,
    )
    
    print("\n" + "=" * 60)
    if results["success"]:
        print(f"✅ Skill indexed successfully!")
        print(f"   Skill ID: {results['skill_id']}")
        print(f"   Log file: {results['log_file']}")
    else:
        print(f"⚠️  Processing completed with errors:")
        for error in results["errors"]:
            print(f"   - {error}")
    print("=" * 60 + "\n")
    
    return results


def cmd_record_start(args):
    """Start recording a workflow."""
    from gui_agents.s3.recording import Recorder
    
    print("\n" + "=" * 60)
    print("🎬 Agent-S Workflow Recorder")
    print("=" * 60)
    print(f"Recording: {args.name or 'unnamed'}")
    print(f"Mode: {args.mode}")
    print("=" * 60)
    print("\nPress Ctrl+C to stop recording...\n")
    
    # Create recorder with optional auto-processing callback
    callback = None if args.no_process else _auto_process_recording
    
    recorder = Recorder(
        recording_name=args.name,
        mode=args.mode,
        capture_screenshots=(args.mode == "screenshots"),
        on_recording_stopped=callback,
    )
    
    recorder.start()
    
    try:
        while recorder.is_recording:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping recording...")
    
    recording_path = recorder.stop()
    
    print(f"\n📁 Recording saved to: {recording_path}")
    
    # If auto-processing is disabled, inform the user
    if args.no_process:
        print("\n💡 Tip: Run 'agent_s record process' to analyze this recording")
    
    return 0


def cmd_record_list(args):
    """List all recordings."""
    from gui_agents.s3.recording import get_recordings_dir
    
    recordings_dir = get_recordings_dir()
    print(f"\n📁 Recordings directory: {recordings_dir}\n")
    
    recordings = sorted(
        [d for d in recordings_dir.iterdir() if d.is_dir()],
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    
    if not recordings:
        print("No recordings found.")
        print("\n💡 Tip: Run 'agent_s record start --name \"my task\"' to create one")
        return 0
    
    print(f"Found {len(recordings)} recording(s):\n")
    
    for i, r in enumerate(recordings[:20], 1):
        metadata_path = r / "metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text())
                duration = metadata.get("duration_seconds", 0)
                mode = metadata.get("capture_mode", "unknown")
                has_log = (r / "log.md").exists()
                status = "✅ processed" if has_log else "⏳ pending"
                print(f"  {i:2d}. {r.name}")
                print(f"      Duration: {duration:.1f}s | Mode: {mode} | {status}")
            except Exception:
                print(f"  {i:2d}. {r.name}")
        else:
            print(f"  {i:2d}. {r.name}")
    
    if len(recordings) > 20:
        print(f"\n  ... and {len(recordings) - 20} more")
    
    return 0


def cmd_record_process(args):
    """Process a recording into a skill."""
    from gui_agents.s3.recording import process_recording, get_latest_recording
    
    # Determine recording path
    if args.recording:
        recording_path = Path(args.recording).expanduser().resolve()
    else:
        recording_path = get_latest_recording()
        if not recording_path:
            print("❌ No recordings found. Specify a path or record first.")
            return 1
        print(f"📁 Using latest recording: {recording_path.name}")
    
    if not recording_path.exists():
        print(f"❌ Recording not found: {recording_path}")
        return 1
    
    print(f"\n🔄 Processing: {recording_path}")
    
    def progress_callback(msg: str, pct: int):
        print(f"[{pct:3d}%] {msg}")
    
    def error_callback(stage: str, e: Exception):
        print(f"⚠️  Error in {stage}: {e}")
    
    results = process_recording(
        recording_path,
        on_progress=progress_callback,
        on_error=error_callback,
    )
    
    print("\n" + "=" * 60)
    if results["success"]:
        print(f"✅ SUCCESS")
        print(f"   Skill ID: {results['skill_id']}")
        print(f"   Log file: {results['log_file']}")
    else:
        print(f"⚠️  FAILED")
        for error in results["errors"]:
            print(f"   - {error}")
    print("=" * 60)
    
    return 0 if results["success"] else 1


def cmd_record_analyze(args):
    """Run only the LLM analysis step on a recording."""
    from gui_agents.s3.recording import analyze_recording, get_latest_recording
    import os
    
    # Determine recording path
    if args.recording:
        recording_path = Path(args.recording).expanduser().resolve()
    else:
        recording_path = get_latest_recording()
        if not recording_path:
            print("❌ No recordings found. Specify a path or record first.")
            return 1
        print(f"📁 Using latest recording: {recording_path.name}")
    
    if not recording_path.exists():
        print(f"❌ Recording not found: {recording_path}")
        return 1
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY environment variable not set")
        return 1
    
    print(f"\n🔄 Analyzing: {recording_path}")
    print(f"   Model: {args.model}")
    
    try:
        # Find video or use directory for screenshots
        video_file = None
        for ext in [".mp4", ".mkv", ".webm", ".mov"]:
            for f in recording_path.glob(f"*{ext}"):
                video_file = f
                break
        
        source = video_file if video_file else recording_path
        
        result = analyze_recording(
            recording_path=source,
            api_key=api_key,
            model=args.model,
            recording_name=recording_path.name,
        )
        
        # Save results
        log_path = recording_path / "log.md"
        log_path.write_text(result, encoding="utf-8")
        
        print(f"\n✅ Analysis complete!")
        print(f"   Saved to: {log_path}")
        
        if args.show:
            print("\n" + "=" * 60)
            print(result[:2000])
            if len(result) > 2000:
                print(f"\n... ({len(result) - 2000} more characters)")
            print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return 1


def add_record_arguments(parser):
    """Add arguments for the record command."""
    subparsers = parser.add_subparsers(dest="record_action", help="Recording actions")
    
    # Start subcommand
    start_parser = subparsers.add_parser("start", help="Start recording a workflow")
    start_parser.add_argument(
        "--name", "-n",
        type=str,
        default=None,
        help="Name for the recording (used for goal identification)",
    )
    start_parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["video", "screenshots"],
        default="video",
        help="Recording mode: video (default) or screenshots",
    )
    start_parser.add_argument(
        "--no-process",
        action="store_true",
        help="Skip automatic post-recording analysis",
    )
    
    # List subcommand
    subparsers.add_parser("list", help="List all recordings")
    
    # Process subcommand
    process_parser = subparsers.add_parser("process", help="Process a recording into a skill")
    process_parser.add_argument(
        "recording",
        type=str,
        nargs="?",
        default=None,
        help="Path to recording directory (default: latest)",
    )
    
    # Analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", help="Run LLM analysis on a recording")
    analyze_parser.add_argument(
        "recording",
        type=str,
        nargs="?",
        default=None,
        help="Path to recording directory (default: latest)",
    )
    analyze_parser.add_argument(
        "--model",
        type=str,
        default="google/gemini-2.0-flash-001",
        help="Model to use for analysis",
    )
    analyze_parser.add_argument(
        "--show",
        action="store_true",
        help="Print analysis output",
    )


def cmd_record(args):
    """Handle record command dispatch."""
    if not hasattr(args, "record_action") or args.record_action is None:
        print("Usage: agent_s record {start|list|process|analyze}")
        print("\nCommands:")
        print("  start    Start recording a workflow")
        print("  list     List all recordings")
        print("  process  Process a recording into a skill")
        print("  analyze  Run LLM analysis on a recording")
        return 1
    
    if args.record_action == "start":
        return cmd_record_start(args)
    elif args.record_action == "list":
        return cmd_record_list(args)
    elif args.record_action == "process":
        return cmd_record_process(args)
    elif args.record_action == "analyze":
        return cmd_record_analyze(args)
    else:
        print(f"Unknown record action: {args.record_action}")
        return 1
