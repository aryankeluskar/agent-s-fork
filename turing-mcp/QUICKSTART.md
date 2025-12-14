# Quick Start Guide

## 1. Prerequisites Check

Ensure you have:
- ✅ Python 3.10 or later
- ✅ Agent-S repository cloned
- ✅ Grounding model endpoint URL
- ✅ API keys for OpenAI/Anthropic/Gemini

## 2. Install Dependencies

```bash
cd /Users/aryank/Developer/Agent-S/turing-mcp

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## 3. Set Up Environment

```bash
# Set PYTHONPATH to include Agent-S
export PYTHONPATH="/Users/aryank/Developer/Agent-S:$PYTHONPATH"

# Or add to your shell profile (~/.zshrc or ~/.bash_profile)
echo 'export PYTHONPATH="/Users/aryank/Developer/Agent-S:$PYTHONPATH"' >> ~/.zshrc
source ~/.zshrc
```

## 4. Configure Grounding Model

You need a grounding model endpoint. Options:

### Option A: Use Modal Deployment

If you have UI-TARS deployed on Modal:

```json
{
  "ground_provider": "openai",
  "ground_model": "uitars-7b",
  "ground_url": "https://your-app--serve-model.modal.run/v1",
  "ground_api_key": null
}
```

### Option B: Use HuggingFace Endpoint

```json
{
  "ground_provider": "huggingface",
  "ground_model": "uitars-7b",
  "ground_url": "https://your-endpoint.huggingface.co/v1",
  "ground_api_key": "hf_..."
}
```

### Option C: Custom Endpoint

Any OpenAI-compatible endpoint that supports vision:

```json
{
  "ground_provider": "openai",
  "ground_model": "your-model",
  "ground_url": "https://your-endpoint.com/v1",
  "ground_api_key": "your-key"
}
```

## 5. Test in Playground

```bash
cd /Users/aryank/Developer/Agent-S/turing-mcp
uv run playground
```

You'll be prompted to enter configuration. Provide:

1. **model_provider**: `openai`, `anthropic`, or `gemini`
2. **model_name**: e.g., `gpt-4o`, `claude-3-5-sonnet-20241022`, `gemini-2.0-flash-exp`
3. **model_api_key**: Your API key
4. **ground_provider**: Your grounding model provider
5. **ground_url**: Your grounding endpoint URL
6. **grounding_width**: `1120` (recommended)
7. **grounding_height**: `1120` (recommended)

Then test the tools:

```python
# Test 1: Simple task
run_task("Open calculator")

# Test 2: Check status (use task_id from above)
get_status(task_id="abc-123-...")

# Test 3: Cancel task
cancel_task(task_id="abc-123-...")

# Test 4: List resources
# Browse to agent-s://tasks
```

## 6. Configure Claude Desktop

### macOS

Edit: `~/Library/Application Support/Claude/claude_desktop_config.json`

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
        "model_api_key": "sk-...",
        "ground_provider": "openai",
        "ground_model": "uitars-7b",
        "ground_url": "https://...",
        "grounding_width": 1120,
        "grounding_height": 1120,
        "enable_reflection": true,
        "max_steps": 15
      }
    }
  }
}
```

### Windows

Edit: `%APPDATA%\Claude\claude_desktop_config.json`

(Same JSON as above, adjust paths for Windows)

### Linux

Edit: `~/.config/Claude/claude_desktop_config.json`

(Same JSON as above)

## 7. Enable macOS Accessibility (macOS only)

1. Open **System Settings**
2. Go to **Privacy & Security** → **Accessibility**
3. Click the **+** button
4. Add **Terminal** (or your IDE)
5. Restart the application

## 8. Restart Claude Desktop

After saving the config:

1. **Quit** Claude Desktop completely (Cmd+Q on macOS)
2. **Reopen** Claude Desktop
3. Check the MCP icon (🔌) in Claude - should show "agent-s" server

## 9. Test in Claude

Try these prompts:

### Test 1: Simple Calculator
```
Can you open the calculator app and compute 25 * 40?
```

Claude should:
1. Call `run_task` with the instruction
2. Show progress updates in real-time
3. Report when task completes

### Test 2: Check Status
```
What's the status of the task?
```

Claude should call `get_status` and show:
- Current step
- Plan history
- Latest screenshot (optional)

### Test 3: Web Browsing
```
Open Chrome and search for "Agent-S paper"
```

## 10. Troubleshooting

### Error: "Failed to initialize Agent-S"

**Check:**
- PYTHONPATH includes Agent-S directory
- All dependencies installed (`uv sync` or `pip install -e .`)
- Grounding model endpoint is accessible

**Test grounding endpoint:**
```bash
curl -X POST https://your-endpoint/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "uitars-7b",
    "messages": [{"role": "user", "content": "test"}]
  }'
```

### Error: "Grounding model validation failed"

**Common causes:**
1. **Wrong URL**: Check `ground_url` points to the correct endpoint
2. **Missing API key**: Add `ground_api_key` if using HuggingFace
3. **Endpoint down**: Verify endpoint is running and accessible
4. **Wrong provider**: Try changing `ground_provider` to `openai` or `huggingface`

### Error: "Task stuck at step X"

**Solutions:**
1. Cancel task: `cancel_task(task_id="...")`
2. Check screenshot: `get_status(task_id="...")` to see what went wrong
3. Increase `max_steps` if task is complex
4. Simplify instruction (break into smaller tasks)

### Error: "Permission denied" (macOS)

**Solution:**
Enable Accessibility permissions (see Step 7)

### MCP Server Not Showing in Claude

**Check:**
1. Config file saved correctly
2. Claude Desktop fully restarted
3. No JSON syntax errors in config
4. Correct path to turing-mcp directory

**Debug:**
Check Claude logs:
```bash
# macOS
tail -f ~/Library/Logs/Claude/mcp*.log

# Check for errors related to agent-s server
```

## 11. Next Steps

Once everything works:

1. **Try complex tasks**: Multi-step workflows
2. **Check plan history**: See how Agent-S breaks down tasks
3. **Monitor screenshots**: Track execution visually
4. **Adjust max_steps**: Tune for your tasks
5. **Enable reflection**: Set `enable_reflection: true` for better planning

## Common Tasks

### Calculator Operations
```
Open calculator and compute X + Y
```

### Web Navigation
```
Open Chrome/Safari and go to example.com
```

### File Operations
```
Create a new text file and type "Hello World"
```

### Application Switching
```
Switch to Finder and create a new folder
```

## Performance Tips

1. **Start simple**: Test with calculator before complex tasks
2. **Monitor progress**: Use `get_status` to track execution
3. **Set realistic max_steps**: 15 steps good for most tasks
4. **Enable reflection**: Improves planning quality
5. **Check screenshots**: Verify agent sees what you expect

## Getting Help

If you encounter issues:

1. Check logs in `turing-mcp/logs/` directory
2. Review error messages carefully
3. Test grounding endpoint independently
4. Verify all configuration values
5. Try simpler tasks first to isolate issues

## Success Checklist

✅ Dependencies installed  
✅ PYTHONPATH configured  
✅ Grounding model validated  
✅ Accessibility enabled (macOS)  
✅ Claude Desktop config updated  
✅ Claude Desktop restarted  
✅ MCP server visible in Claude  
✅ Simple task executed successfully  

Congratulations! You're ready to use Agent-S through MCP! 🎉
