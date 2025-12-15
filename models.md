## ⚠️ CRITICAL: Vision Requirements for Agent-S

**Agent-S is a GUI agent that REQUIRES vision/multimodal support** to process screenshots of your screen. Not all models support vision!

### Vision-Capable Models (Required for Main Model)

These models can process images and MUST be used for the main Agent-S model:

1. **OpenAI** (Recommended for reliability)

```
export OPENAI_API_KEY=<YOUR_API_KEY>
```

Vision models:
- `gpt-4o` - Fast, reliable, vision-capable (recommended for Agent-S)
- `gpt-4-turbo` - Powerful vision capabilities
- `gpt-5-nano-2025-08-07` - Latest with vision support

2. **Anthropic**

```
export ANTHROPIC_API_KEY=<YOUR_API_KEY>
```

Vision models:
- `claude-3-5-sonnet-20241022` - Excellent vision and reasoning
- `claude-3-opus-20240229` - Most capable, slower

3. **Google Gemini**

```
export GEMINI_API_KEY=<YOUR_API_KEY>
export GEMINI_ENDPOINT_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
```

Vision models:
- `gemini-1.5-pro` - High-quality vision
- `gemini-1.5-flash` - Fast vision processing

### Text-Only Models (Reflection Model Only)

These models are **text-only** and can ONLY be used for the reflection model (not main model):

1. **Cerebras** (Recommended for fast, cheap reflection)

```
export CEREBRAS_API_KEY=<YOUR_API_KEY>
```

Get your API key at: https://inference.cerebras.ai/

Text-only models:
- `qwen-3-32b` - Ultra-fast, perfect for reflection tasks (recommended)
- `qwen-3-235b-a22b-instruct-2507` - High-quality reasoning, text-only
- `llama-3.3-70b` - Strong performance, text-only

**⚠️ WARNING**: Cerebras models do NOT support vision. Attempting to send images will result in 500 errors!

2. OpenAI

```
export OPENAI_API_KEY=<YOUR_API_KEY>
```

3. Anthropic

```
export ANTHROPIC_API_KEY=<YOUR_API_KEY>
```

3. Gemini

```
export GEMINI_API_KEY=<YOUR_API_KEY>
export GEMINI_ENDPOINT_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
```

4. OpenAI on Azure

```
export AZURE_OPENAI_API_BASE=<DEPLOYMENT_NAME>
export AZURE_OPENAI_API_KEY=<YOUR_API_KEY>
```

5. vLLM for Local Models

```
export vLLM_ENDPOINT_URL=<YOUR_DEPLOYMENT_URL>
```

Alternatively you can directly pass the API keys into the engine_params argument while instantating the agent.

6. Open Router

```
export OPENROUTER_API_KEY=<YOUR_API_KEY>
export OPEN_ROUTER_ENDPOINT_URL="https://openrouter.ai/api/v1"
```

## Usage Examples

### Recommended: OpenAI (Main) + Cerebras (Reflection)

This configuration provides the **best balance of speed, quality, and cost**:

```python
from gui_agents.s3.agents.agent_s import AgentS3

# Main model: Vision-capable OpenAI model
engine_params = {
    "engine_type": 'openai',
    "model": 'gpt-4o', # Vision-capable for processing screenshots
}

# Reflection model: Ultra-fast Cerebras (text-only)
reflection_engine_params = {
    "engine_type": 'cerebras',
    "model": 'qwen-3-32b', # Fast, cheap, perfect for reflection
}

agent = AgentS3(
    engine_params,
    grounding_agent,
    platform=current_platform,
    reflection_engine_params=reflection_engine_params,
)
```

**Why This Configuration?**
- ✅ **Main Model (gpt-4o)**: Supports vision to process screenshots
- ✅ **Reflection Model (qwen-3-32b)**: Ultra-fast, text-only, ~70% cheaper
- ✅ **Best Performance**: Vision where needed, speed where possible

### Using OpenAI

```python
from gui_agents.s3.agents.agent_s import AgentS3

engine_params = {
    "engine_type": 'openai', # Allowed Values: 'cerebras', 'openai', 'anthropic', 'gemini', 'azure_openai', 'vllm', 'open_router'
    "model": 'gpt-5-2025-08-07', # Allowed Values: Any Vision and Language Model from the supported APIs
}
agent = AgentS3(
    engine_params,
    grounding_agent,
    platform=current_platform,
)
```

To use the underlying Multimodal Agent (LMMAgent) which wraps LLMs with message handling functionality, you can use the following code snippet:

```python
from gui_agents.s3.core.mllm import LMMAgent

engine_params = {
    "engine_type": 'cerebras', # Allowed Values: 'cerebras', 'openai', 'anthropic', 'gemini', 'azure_openai', 'vllm', 'open_router'
    "model": 'qwen-3-235b-a22b-instruct-2507', # Allowed Values: Any Vision and Language Model from the supported APIs
}
agent = LMMAgent(
    engine_params=engine_params,
)
```

The `AgentS3` also utilizes this `LMMAgent` internally.