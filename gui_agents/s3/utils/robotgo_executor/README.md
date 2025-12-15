# Robotgo Executor

A Go binary that executes GUI automation commands using robotgo, replacing pyautogui functionality. Based on patterns from the turing project.

## Building

### Quick Build
```bash
cd gui_agents/s3/utils/robotgo_executor
chmod +x build.sh
./build.sh
```

### Manual Build
```bash
cd gui_agents/s3/utils/robotgo_executor
go mod tidy
go build -o robotgo_executor main.go
```

## Usage

The binary accepts JSON commands via command-line flag:

```bash
./robotgo_executor -json '{"type":"click","params":{"x":100,"y":200,"button":"left"}}' -platform darwin
```

## Supported Actions

- `click`: Click at coordinates (supports clicks count, button type, hold_keys)
- `moveTo`: Move mouse to coordinates
- `dragTo`: Drag from (x1,y1) to (x2,y2) with optional button and hold_keys
- `type`/`write`: Type text
- `press`: Press a single key
- `hotkey`: Press key combination (e.g., ["cmd", "c"])
- `keyDown`/`keyUp`: Hold/release keys
- `scroll`: Scroll at coordinates (supports horizontal flag)
- `wait`: Wait for duration in seconds
- `screenSize`: Get screen dimensions (returns JSON)

## Example JSON Commands

```json
{"type":"click","params":{"x":100,"y":200,"button":"left","clicks":1}}
{"type":"hotkey","params":{"keys":["cmd","c"]},"platform":"darwin"}
{"type":"type","params":{"text":"Hello World"}}
{"type":"scroll","params":{"x":500,"y":500,"clicks":3,"horizontal":false}}
{"type":"wait","params":{"duration":1.5}}
```

## Integration with Agent S3

Use the `--use_robotgo` flag when running Agent S3:

```bash
agent_s --use_robotgo --provider openai --model gpt-5-2025-08-07 ...
```

The Python wrapper (`robotgo_executor.py`) will automatically parse pyautogui code strings and convert them to robotgo JSON commands.

