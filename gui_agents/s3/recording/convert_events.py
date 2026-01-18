"""
Event Converter for Agent-S

Converts raw events.jsonl files into human-readable actions.txt format
for use by the recording analyzer.
"""

import json
from pathlib import Path
from typing import List, Dict


def load_events(events_path: Path) -> List[Dict]:
    """
    Load events from a JSONL file.
    
    Args:
        events_path: Path to events.jsonl file
        
    Returns:
        List of event dictionaries
    """
    events = []
    with open(events_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def _get_action_type(event: Dict) -> str:
    """Get action type from event, handling both 'type' and 'action' keys."""
    # Handle raw pynput format ("type") and internal format ("action")
    action = event.get("action") or event.get("type", "")
    
    # Normalize action names
    if action == "key":
        # Raw key event - check if pressed
        if event.get("pressed", True):
            return "press"
        return "release"
    
    return action


def simplify_events(events: List[Dict]) -> List[Dict]:
    """
    Simplify raw events by:
    - Merging consecutive typing into single text events
    - Removing redundant mouse moves
    - Consolidating repeated scrolls
    
    Args:
        events: List of raw event dictionaries
        
    Returns:
        Simplified list of events
    """
    simplified = []
    i = 0
    
    while i < len(events):
        event = events[i]
        action = _get_action_type(event)
        
        # Skip redundant consecutive mouse moves (keep every 10th or before clicks)
        if action == "move":
            # Look ahead - if next is also move, skip this one
            if i + 1 < len(events) and _get_action_type(events[i + 1]) == "move":
                i += 1
                continue
        
        # Merge consecutive key presses into text typing
        if action in ["press", "release"]:
            key = event.get("key", "")
            
            # Check if this is a printable character
            if key and len(key) == 1 and key.isprintable():
                text_buffer = key if action == "press" else ""
                j = i + 1
                
                while j < len(events):
                    next_event = events[j]
                    next_action = _get_action_type(next_event)
                    
                    if next_action == "press":
                        next_key = next_event.get("key", "")
                        if next_key and len(next_key) == 1 and next_key.isprintable():
                            text_buffer += next_key
                            j += 1
                        else:
                            break
                    elif next_action == "release":
                        j += 1
                    else:
                        break
                
                # If we accumulated multiple characters, create a typing event
                if len(text_buffer) > 1:
                    simplified.append({
                        "action": "type",
                        "text": text_buffer,
                        "time_stamp": event.get("time_stamp", event.get("time", 0))
                    })
                    i = j
                    continue
        
        # Consolidate repeated scroll events
        if action == "scroll":
            total_dx = event.get("dx", 0)
            total_dy = event.get("dy", 0)
            j = i + 1
            
            while j < len(events):
                next_event = events[j]
                if _get_action_type(next_event) == "scroll":
                    # Check if scroll is in same direction and within 0.5 seconds
                    time_diff = next_event.get("time_stamp", next_event.get("time", 0)) - event.get("time_stamp", event.get("time", 0))
                    if time_diff < 0.5:
                        total_dx += next_event.get("dx", 0)
                        total_dy += next_event.get("dy", 0)
                        j += 1
                    else:
                        break
                else:
                    break
            
            # Create consolidated scroll event
            if j > i + 1:
                simplified.append({
                    "action": "scroll",
                    "x": event.get("x", 0),
                    "y": event.get("y", 0),
                    "dx": total_dx,
                    "dy": total_dy,
                    "time_stamp": event.get("time_stamp", event.get("time", 0))
                })
                i = j
                continue
        
        # Normalize the event before adding
        normalized = event.copy()
        # Ensure 'action' key exists (normalized from 'type')
        if "action" not in normalized and "type" in normalized:
            normalized["action"] = _get_action_type(event)
        simplified.append(normalized)
        i += 1
    
    return simplified


def convert_events(events: List[Dict]) -> List[str]:
    """
    Convert event list to human-readable action strings.
    
    Handles both raw pynput format (with "type" key) and
    internal format (with "action" key).
    
    Args:
        events: List of (optionally simplified) event dictionaries
        
    Returns:
        List of action strings
    """
    actions = []
    action_num = 1
    
    pending_move = None
    i = 0
    
    while i < len(events):
        event = events[i]
        action_type = _get_action_type(event)
        
        if action_type == "click":
            pressed = event.get("pressed", True)
            if not pressed:
                i += 1
                continue
            
            x = int(event.get("x", 0))
            y = int(event.get("y", 0))
            button = str(event.get("button", "left")).upper()
            # Handle Button.left format from pynput
            if "LEFT" in button:
                button = "LEFT"
            elif "RIGHT" in button:
                button = "RIGHT"
            elif "MIDDLE" in button:
                button = "MIDDLE"
            
            # Count clicks by looking ahead
            num_clicks = 1
            j = i + 1
            while j < len(events):
                next_event = events[j]
                next_button = str(next_event.get("button", "")).upper()
                if ((_get_action_type(next_event) == "click") and 
                    next_event.get("pressed") and
                    button in next_button and
                    abs(next_event.get("x", 0) - x) < 5 and
                    abs(next_event.get("y", 0) - y) < 5):
                    # Check time difference (double click within 0.5s)
                    time_diff = next_event.get("time_stamp", next_event.get("time", 0)) - event.get("time_stamp", event.get("time", 0))
                    if time_diff < 0.5:
                        num_clicks += 1
                        j += 1
                    else:
                        break
                else:
                    break
            
            actions.append(f"{action_num}. CLICK({x}, {y}){{button: {button}, num_clicks: {num_clicks}}}")
            action_num += 1
            pending_move = None
            i = j
            continue
        
        elif action_type == "press":
            key = event.get("key", "")
            if key:
                # Check if it's a special key (not single printable char)
                if len(key) > 1 or not key.isprintable():
                    actions.append(f"{action_num}. PRESS({key})⌨️")
                    action_num += 1
        
        elif action_type == "release":
            pass  # Skip release events
        
        elif action_type == "type":
            text = event.get("text", "")
            if text:
                # Escape quotes in text
                text_escaped = text.replace('"', '\\"')
                actions.append(f'{action_num}. TYPING("{text_escaped}")💻')
                action_num += 1
        
        elif action_type == "move":
            x = int(event.get("x", 0))
            y = int(event.get("y", 0))
            
            # Only record move if followed by drag
            if i + 1 < len(events):
                next_event = events[i + 1]
                if _get_action_type(next_event) == "drag":
                    actions.append(f"{action_num}. MOVE_TO({x}, {y})🕹️")
                    action_num += 1
                    pending_move = (x, y)
        
        elif action_type == "drag":
            x = int(event.get("x", 0))
            y = int(event.get("y", 0))
            
            if pending_move:
                actions.append(f"{action_num}. DRAG_TO({x}, {y})🕹️")
                action_num += 1
                pending_move = None
            else:
                # Standalone drag - record both move and drag
                actions.append(f"{action_num}. DRAG_TO({x}, {y})🕹️")
                action_num += 1
        
        elif action_type == "scroll":
            dy = event.get("dy", 0)
            dx = event.get("dx", 0)
            
            if dy > 0:
                actions.append(f"{action_num}. SCROLL_DOWN({abs(dy)})🔽")
            elif dy < 0:
                actions.append(f"{action_num}. SCROLL_UP({abs(dy)})🔼")
            elif dx > 0:
                actions.append(f"{action_num}. SCROLL_RIGHT({abs(dx)})➡️")
            elif dx < 0:
                actions.append(f"{action_num}. SCROLL_LEFT({abs(dx)})⬅️")
            action_num += 1
        
        elif action_type == "pause":
            actions.append(f"{action_num}. PAUSE⏸️")
            action_num += 1
        
        elif action_type == "resume":
            actions.append(f"{action_num}. RESUME▶️")
            action_num += 1
        
        # Skip screenshot events in action log
        elif action_type == "screenshot":
            pass
        
        i += 1
    
    return actions


def convert_events_file(events_path: Path, output_path: Path = None) -> Path:
    """
    Convert an events.jsonl file to actions.txt.
    
    Args:
        events_path: Path to events.jsonl file
        output_path: Optional output path (defaults to actions.txt in same directory)
        
    Returns:
        Path to the generated actions.txt file
    """
    if output_path is None:
        output_path = events_path.parent / "actions.txt"
    
    # Load and simplify events
    events = load_events(events_path)
    events = simplify_events(events)
    
    # Convert to actions
    actions = convert_events(events)
    
    # Write output
    output_text = "Actions\n" + "\n".join(actions)
    output_path.write_text(output_text)
    
    return output_path


def main():
    """CLI entry point for converting events."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Convert Agent-S events.jsonl to actions.txt format"
    )
    parser.add_argument("events_file", type=Path, help="Path to events.jsonl")
    parser.add_argument("-o", "--output", type=Path, help="Output file path")
    parser.add_argument("--no-simplify", action="store_true", help="Skip event simplification")
    
    args = parser.parse_args()
    
    if not args.events_file.exists():
        print(f"Error: File not found: {args.events_file}")
        return 1
    
    output_path = args.output or args.events_file.parent / "actions.txt"
    
    print(f"Loading events from: {args.events_file}")
    events = load_events(args.events_file)
    print(f"Loaded {len(events)} raw events")
    
    if not args.no_simplify:
        events = simplify_events(events)
        print(f"Simplified to {len(events)} events")
    
    actions = convert_events(events)
    print(f"Converted to {len(actions)} actions")
    
    output_text = "Actions\n" + "\n".join(actions)
    output_path.write_text(output_text)
    print(f"Saved to: {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
