"""
Screen Recording Analyzer for Agent-S

Analyzes screen recordings using multimodal LLMs (via OpenRouter) and generates
detailed automation documentation for Agent-S to learn and replicate workflows.

Usage:
    python analyze.py <video_or_screenshots_dir> [--actions <actions_file>] [--output <output_dir>]
    python analyze.py /path/to/recording/
    python analyze.py /path/to/recording.mp4 --actions /path/to/actions.txt
"""

import argparse
import base64
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv


# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent
PROMPT_PATH = SCRIPT_DIR / "prompt.md"


# Supported formats
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".mpeg", ".mpg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# MIME type mapping
MIME_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".m4v": "video/x-m4v",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def find_and_load_env():
    """Find and load .env file from current or parent directories."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        env_file = parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            return env_file
    
    # Also check script directory and its parents
    for parent in [SCRIPT_DIR] + list(SCRIPT_DIR.parents):
        env_file = parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            return env_file
    return None


find_and_load_env()


def load_prompt() -> str:
    """Load the analysis prompt from prompt.md."""
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def encode_file_base64(file_path: Path) -> str:
    """Encode a file to base64 string."""
    with open(file_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_mime_type(file_path: Path) -> str:
    """Get MIME type for a file."""
    ext = file_path.suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


def clean_response_text(response: str) -> str:
    """
    Remove filler sentences from the beginning of LLM responses.
    
    Looks for patterns like acknowledgements, confirmations, or introductory
    sentences that appear before the structured content.
    """
    lines = response.strip().split('\n')
    
    # Common filler sentence starters to remove
    filler_starts = [
        "okay", "i will", "i'll", "let me", "sure,", "certainly",
        "here's", "here is", "below is", "i have", "i've",
        "the workflow", "this workflow", "as requested"
    ]
    
    # Find the line that starts the actual structured content
    content_start_idx = None
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Check if this is the start of structured content
        if line.startswith('# Workflow:') or line.startswith('### ') or line.startswith('## '):
            content_start_idx = i
            break
        
        # Check if this line looks like filler
        is_filler = any(line_lower.startswith(start) for start in filler_starts)
        if not is_filler and line.strip():
            # If we find a non-filler line that's not structured content, keep it
            break
    
    if content_start_idx is not None:
        # Remove everything before the structured content
        cleaned_lines = lines[content_start_idx:]
    else:
        # If we can't find structured content, try to remove obvious filler
        cleaned_lines = []
        for line in lines:
            line_lower = line.lower().strip()
            # Skip lines that are clearly filler acknowledgements
            if any(line_lower.startswith(start) and len(line.strip()) < 100 for start in filler_starts):
                continue
            cleaned_lines.append(line)
    
    # Join and clean up
    result = '\n'.join(cleaned_lines).strip()
    
    # If result is empty or too short, return original
    if len(result) < 50:
        return response
    
    return result


def get_screenshots_from_directory(directory: Path, max_images: int = 20) -> List[Path]:
    """
    Get screenshot images from a recording directory.
    
    Args:
        directory: Path to recording directory
        max_images: Maximum number of images to include (evenly sampled)
        
    Returns:
        List of paths to screenshot images
    """
    screenshots_dir = directory / "screenshots"
    if not screenshots_dir.exists():
        # Check for images directly in the directory
        screenshots_dir = directory
    
    # Find all image files
    images = []
    for ext in IMAGE_EXTENSIONS:
        images.extend(screenshots_dir.glob(f"*{ext}"))
        images.extend(screenshots_dir.glob(f"*{ext.upper()}"))
    
    # Sort by name (assumes sequential naming like frame_00001.png)
    images = sorted(images)
    
    if not images:
        return []
    
    # Sample evenly if we have too many images
    if len(images) > max_images:
        step = len(images) // max_images
        images = [images[i] for i in range(0, len(images), step)][:max_images]
    
    return images


def analyze_recording(
    recording_path: Path,
    actions_path: Optional[Path] = None,
    api_key: Optional[str] = None,
    model: str = "google/gemini-3-flash-preview",
    recording_name: Optional[str] = None,
    max_images: int = 15,
) -> str:
    """
    Analyze a screen recording and generate automation documentation.
    
    Args:
        recording_path: Path to video file or recording directory with screenshots
        actions_path: Optional path to actions.txt with event data
        api_key: OpenRouter API key (or set OPENROUTER_API_KEY env var)
        model: Model to use (default: gemini-2.0-flash-001)
        recording_name: Name of the recording (used to identify the goal)
        max_images: Maximum number of screenshot images to send (if using screenshots)
        
    Returns:
        Generated markdown documentation
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package required. Install with: pip install openai")
    
    # Get API key
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenRouter API key required. Set OPENROUTER_API_KEY environment variable "
            "or pass api_key parameter."
        )
    
    # Determine if we have a video or directory of screenshots
    is_video = recording_path.is_file() and recording_path.suffix.lower() in VIDEO_EXTENSIONS
    is_directory = recording_path.is_dir()
    
    if not recording_path.exists():
        raise FileNotFoundError(f"Recording not found: {recording_path}")
    
    if not is_video and not is_directory:
        raise ValueError(
            f"Recording must be a video file or directory with screenshots. "
            f"Got: {recording_path}"
        )
    
    # Load prompt
    prompt = load_prompt()
    
    # Add recording name context (this is the user's PRIMARY INTENT)
    if recording_name:
        prompt += f"\n\n## Recording Name (USER'S PRIMARY GOAL)\n\n**Recording Name**: `{recording_name}`\n\nThis is what the user intended to record. Focus ONLY on actions that accomplish this goal. Exclude:\n1. Recording software actions (Agent-S Recorder, OBS, screen recording controls)\n2. Actions that happen AFTER the goal is achieved (post-goal browsing/exploration)"
    
    # Load actions if provided
    actions_content = ""
    if actions_path and actions_path.exists():
        actions_content = actions_path.read_text(encoding="utf-8")
        prompt += f"\n\n## Recorded Event Data\n\nThe following events were captured during the recording:\n\n```\n{actions_content}\n```"
    
    # Auto-detect actions.txt if not provided
    if not actions_content and is_directory:
        potential_actions = recording_path / "actions.txt"
        if potential_actions.exists():
            actions_content = potential_actions.read_text(encoding="utf-8")
            prompt += f"\n\n## Recorded Event Data\n\nThe following events were captured during the recording:\n\n```\n{actions_content}\n```"
            print(f"Found actions file: {potential_actions}")
    
    # Build message content
    content = [
        {
            "type": "text",
            "text": prompt,
        }
    ]
    
    # Add visual content
    if is_video:
        print(f"Encoding video: {recording_path.name}...")
        video_base64 = encode_file_base64(recording_path)
        mime_type = get_mime_type(recording_path)
        print(f"Video encoded ({len(video_base64) / 1024 / 1024:.1f} MB base64)")
        
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{video_base64}",
            },
        })
    else:
        # Get screenshots from directory
        screenshots = get_screenshots_from_directory(recording_path, max_images=max_images)
        
        if not screenshots:
            print("Warning: No screenshots found in recording directory")
        else:
            print(f"Found {len(screenshots)} screenshots")
            
            for screenshot in screenshots:
                image_base64 = encode_file_base64(screenshot)
                mime_type = get_mime_type(screenshot)
                
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_base64}",
                    },
                })
    
    # Initialize OpenAI client for OpenRouter
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    
    # Call API
    print(f"Analyzing with {model}...")
    completion = client.chat.completions.create(
        extra_headers={
            "HTTP-Referer": "https://github.com/simular-ai/Agent-S",
            "X-Title": "Agent-S Workflow Analyzer",
        },
        model=model,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        max_tokens=8192,
    )
    
    result = completion.choices[0].message.content
    print("Analysis complete!")
    
    # Clean up filler sentences from the beginning
    result = clean_response_text(result)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Analyze screen recordings for Agent-S automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s /path/to/recording/
    %(prog)s recording.mp4
    %(prog)s recording.mp4 --actions actions.txt
    %(prog)s /path/to/recording/ --output ./output/
    %(prog)s recording.mp4 --model google/gemini-2.5-pro-preview
        """,
    )
    parser.add_argument(
        "recording",
        type=Path,
        help="Path to screen recording video file or directory with screenshots",
    )
    parser.add_argument(
        "--actions", "-a",
        type=Path,
        help="Path to actions.txt file with recorded events",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output directory for results (default: same as recording)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="google/gemini-3-flash-preview",
        help="Model to use (default: google/gemini-3-flash-preview)",
    )
    parser.add_argument(
        "--api-key", "-k",
        type=str,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env var)",
    )
    parser.add_argument(
        "--name", "-n",
        type=str,
        help="Recording name (overrides folder name for goal identification)",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=15,
        help="Maximum number of screenshot images to include (default: 15)",
    )
    
    args = parser.parse_args()
    
    try:
        # Resolve paths
        recording_path = args.recording.resolve()
        actions_path = args.actions.resolve() if args.actions else None
        
        # Determine recording name
        recording_name = args.name or recording_path.name
        
        # Analyze recording
        result = analyze_recording(
            recording_path=recording_path,
            actions_path=actions_path,
            api_key=args.api_key,
            model=args.model,
            recording_name=recording_name,
            max_images=args.max_images,
        )
        
        # Determine output directory
        if args.output:
            output_dir = args.output.resolve()
        elif recording_path.is_dir():
            output_dir = recording_path
        else:
            output_dir = recording_path.parent
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save results
        log_path = output_dir / "log.md"
        log_path.write_text(result, encoding="utf-8")
        print(f"Saved analysis to: {log_path}")
        
        print(f"\nOutput directory: {output_dir}")
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
