# Agent-S MCP Server

Model Context Protocol (MCP) server for controlling Agent-S GUI automation directly from Claude Desktop and other MCP clients.

## Features

- **Full GUI Automation**: Execute multi-step GUI tasks with natural language instructions
- **Real-time Progress**: Stream execution progress with live updates
- **Screenshot Capture**: Automatic screenshot capture at each step
- **Server-side Execution**: All actions execute locally with pyautogui
- **Task Management**: Query status, view history, and cancel running tasks

## Architecture

```
┌─────────────────┐
│  MCP Client     │  (Claude Desktop, etc.)
│  (Claude, etc.) │
└────────┬────────┘
         │ MCP Protocol
         ▼
┌─────────────────┐
│  Agent-S Server │  (This package)
│  - 3 Tools      │
│  - 2 Resources  │
└────────┬────────┘
         │ Direct Python Integration
         ▼
┌─────────────────┐
│   Agent-S       │  (GUI Automation)
│   - Worker      │
│   - Grounding   │
│   - Reflection  │
└─────────────────┘
```

## Prerequisites

1. **Python 3.10+**
2. **Agent-S installed** - Must be in Python path
3. **Grounding Model Endpoint** - UI-TARS or compatible model
4. **API Keys** - For OpenAI/Anthropic/Gemini models

### macOS Specific

Enable accessibility permissions for Terminal/IDE:
```bash
System Settings > Privacy & Security > Accessibility
```

Add your terminal/IDE to the allowed applications.

## Installation

```bash
cd /Users/aryank/Developer/Agent-S/turing-mcp

# Install dependencies
uv sync

# Or with pip
pip install -e .
```

## Configuration

The server requires session-level configuration provided by the MCP client. Configure in your MCP client settings:

### Required Configuration

```json
{
  "model_provider": "openai",
  "model_name": "gpt-4o",
  "model_api_key": "sk-...",
  
  "ground_provider": "openai",
  "ground_model": "uitars-7b",
  "ground_url": "https://your-grounding-endpoint.com/v1",
  "ground_api_key": "optional-if-needed",
  "grounding_width": 1120,
  "grounding_height": 1120,
  
  "enable_reflection": true,
  "max_steps": 15
}
```

### Optional Configuration

```json
{
  "model_url": "https://custom-openai-endpoint.com/v1",
  "model_temperature": 0.7,
  "max_trajectory_length": 8,
  "enable_local_env": false
}
```

## Usage

### Development Mode

Run with interactive testing:

```bash
cd /Users/aryank/Developer/Agent-S/turing-mcp
uv run playground
```

### Claude Desktop Integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agent-s": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/aryank/Developer/Agent-S/turing-mcp",
        "run",
        "start"
      ],
      "env": {
        "PYTHONPATH": "/Users/aryank/Developer/Agent-S"
      },
      "config": {
        "model_provider": "openai",
        "model_name": "gpt-4o",
        "model_api_key": "YOUR_API_KEY",
        "ground_provider": "openai",
        "ground_model": "uitars-7b",
        "ground_url": "YOUR_GROUNDING_ENDPOINT",
        "ground_api_key": "YOUR_GROUNDING_KEY",
        "grounding_width": 1120,
        "grounding_height": 1120,
        "enable_reflection": true,
        "max_steps": 15
      }
    }
  }
}
```

Restart Claude Desktop after configuration.

## API Reference

### Tools

#### `run_task(instruction: str) -> JSON`

Execute a GUI automation task.

**Arguments:**
- `instruction`: Natural language task description

**Returns:**
```json
{
  "task_id": "uuid",
  "status": "running",
  "message": "Task started with 15 max steps"
}
```

**Example:**
```
run_task("Open calculator and compute 123 + 456")
```

#### `get_status(task_id: str) -> JSON`

Query task status and progress.

**Returns:**
```json
{
  "task_id": "uuid",
  "status": "running",
  "current_step": 5,
  "max_steps": 15,
  "plan_history": [
    "Step 1: Open calculator application",
    "Step 2: Click on number 1",
    ...
  ],
  "latest_screenshot": "base64_encoded_png",
  "error": null
}
```

#### `cancel_task(task_id: str) -> JSON`

Cancel a running task.

**Returns:**
```json
{
  "task_id": "uuid",
  "status": "cancelled",
  "message": "Task cancelled successfully"
}
```

### Resources

#### `agent-s://tasks`

List all tasks for the session.

#### `agent-s://screenshot/{task_id}`

Get the latest screenshot for a task.

### Prompts

#### `automate_task(task_description: str)`

Generate a structured prompt for GUI automation.

## Examples

### Simple Task

```
User: Can you open the calculator and compute 50 * 23?

Claude: I'll use Agent-S to automate this task.
[Calls run_task("Open calculator and compute 50 * 23")]

Result: Task started with ID abc-123
[Real-time progress updates shown]
Step 1/15: Opening calculator application...
Step 2/15: Clicking on 5...
Step 3/15: Clicking on 0...
...
Task completed successfully!
```

### Web Browsing

```
User: Open Chrome and search for "Agent-S paper"

[Agent-S will:]
1. Open Chrome application
2. Click address bar
3. Type search query
4. Press Enter
5. Mark task as complete
```

### Check Status

```
User: What's the status of task abc-123?

[Call get_status(task_id="abc-123")]
Returns: Current step, plan history, latest screenshot
```

## Troubleshooting

### Grounding Model Connection Failed

```
Error: ❌ Grounding model validation failed!
```

**Solutions:**
1. Check `ground_url` is accessible
2. Verify `ground_api_key` if using HuggingFace
3. For Modal endpoints, ensure endpoint is deployed
4. Test endpoint manually: `curl -X POST <ground_url>/v1/chat/completions`

### Accessibility Permissions (macOS)

```
Error: pyautogui.FailSafeException
```

**Solution:**
1. Open System Settings
2. Go to Privacy & Security > Accessibility
3. Add Terminal or your IDE to allowed apps
4. Restart the application

### Task Stuck

```
Status: Task has been running for a long time
```

**Solutions:**
1. Use `cancel_task(task_id)` to stop
2. Check latest screenshot with `get_status(task_id)`
3. Adjust `max_steps` if task is complex
4. Simplify task instruction

### Import Errors

```
Error: No module named 'gui_agents'
```

**Solution:**
Set `PYTHONPATH` to include Agent-S:
```bash
export PYTHONPATH="/Users/aryank/Developer/Agent-S:$PYTHONPATH"
```

Or in Claude Desktop config:
```json
{
  "env": {
    "PYTHONPATH": "/Users/aryank/Developer/Agent-S"
  }
}
```

## Development

### Project Structure

```
turing-mcp/
├── src/
│   └── agent_s_server/
│       ├── __init__.py
│       ├── server.py          # Main MCP server (3 tools, 2 resources)
│       ├── models.py           # Pydantic models
│       ├── task_manager.py     # Thread-safe state management
│       └── agent_wrapper.py    # Agent-S execution wrapper
├── pyproject.toml
├── smithery.yaml
└── README.md
```

### Testing Locally

```bash
# Install dependencies
cd /Users/aryank/Developer/Agent-S/turing-mcp
uv sync

# Run playground
uv run playground

# In playground, test:
> run_task("Open calculator")
> get_status(task_id="...")
> cancel_task(task_id="...")
```

### Adding New Tools

1. Edit `src/agent_s_server/server.py`
2. Add new `@server.tool()` decorated function
3. Update documentation
4. Test in playground

## Performance

- **Single task limit**: Phase 1 enforces one task at a time
- **Memory management**: Only latest screenshot stored per task
- **Cleanup**: Tasks older than 24 hours auto-deleted
- **Screenshot size**: Scaled to 2400px max dimension

## Security Considerations

⚠️ **Important Security Notes:**

1. **Code Execution**: Agent-S executes arbitrary code locally using `exec()`
2. **Accessibility**: Requires full accessibility permissions
3. **API Keys**: Stored in MCP client config (not logged by server)
4. **Screenshots**: May contain sensitive information
5. **Local Environment**: Only enable `enable_local_env` if you trust the LLM

**Recommendations:**
- Run in isolated environment
- Use dedicated machine for automation
- Review task instructions before execution
- Monitor task execution with `get_status`
- Use `cancel_task` if unexpected behavior

## Roadmap

- [ ] Phase 1: Single task execution ✅
- [ ] Phase 2: Parallel task execution with process pool
- [ ] Phase 3: Task scheduling and queuing
- [ ] Phase 4: Enhanced error recovery
- [ ] Phase 5: Task templates and workflows

## Contributing

Contributions welcome! Please:
1. Follow existing code structure
2. Add tests for new features
3. Update documentation
4. Test with Claude Desktop integration

## License

See LICENSE file in Agent-S repository.

## Support

For issues:
1. Check troubleshooting section
2. Review logs in `logs/` directory
3. Open issue on Agent-S GitHub
4. Include error messages and configuration (redact API keys)

## Acknowledgments

Built with:
- [Agent-S](https://github.com/simular-ai/Agent-S) - GUI automation framework
- [FastMCP](https://github.com/modelcontextprotocol/python-sdk) - MCP Python SDK
- [Smithery](https://smithery.ai) - MCP server framework
- [PyAutoGUI](https://github.com/asweigart/pyautogui) - GUI automation library