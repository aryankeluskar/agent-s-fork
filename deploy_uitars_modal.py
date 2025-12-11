#!/usr/bin/env python3
"""
Modal deployment for UI-TARS-1.5-7B
Production-ready deployment with Transformers on A100 GPUs.

NOTE: vLLM 0.6.6 does NOT support Qwen2.5-VL architecture (Qwen2_5_VLForConditionalGeneration).
UI-TARS-1.5-7B is based on Qwen2.5-VL, so we must use HuggingFace Transformers.

Based on the working local server implementation.
"""

import modal

# Modal app configuration
app = modal.App("uitars-grounding-server")

# Model configuration
MODEL_NAME = "ByteDance-Seed/UI-TARS-1.5-7B"
MODEL_REVISION = "main"
GROUNDING_WIDTH = 1920
GROUNDING_HEIGHT = 1080

# Create a persistent volume for model caching
# This avoids downloading the 31GB model on every cold start
model_cache = modal.Volume.from_name(
    "uitars-model-cache",
    create_if_missing=True
)

# Define the container image with all dependencies
vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.6.6",  # Latest stable with vision support
        "torch==2.5.1",
        "transformers>=4.48.0",  # Need 4.48+ for Qwen2.5-VL support
        "accelerate==1.2.1",
        "pillow==11.0.0",
        "hf-transfer",  # Fast HuggingFace downloads
        "huggingface_hub",  # For snapshot_download
        "qwen-vl-utils",  # Required for Qwen2.5-VL models
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
    })
)


@app.function(
    image=vllm_image,
    # No secrets needed for downloading public models
    volumes={"/model_cache": model_cache},
    timeout=60 * 60,  # 1 hour for download
)
def download_model():
    """
    Pre-download the model to Modal volume.
    Run this once before deploying the server:
    
    modal run deploy_uitars_modal.py::download_model
    
    Note: This downloads from a public HuggingFace repo, no token needed.
    """
    from huggingface_hub import snapshot_download
    
    print("=" * 60)
    print("📥 Downloading UI-TARS-1.5-7B to Modal Volume")
    print("=" * 60)
    print(f"Model: {MODEL_NAME}")
    print(f"Size: ~31GB")
    print()
    
    snapshot_download(
        MODEL_NAME,
        cache_dir="/model_cache",
        revision=MODEL_REVISION,
        ignore_patterns=["*.md", "*.txt"],
    )
    
    # Commit the volume
    model_cache.commit()
    
    print()
    print("=" * 60)
    print("✅ Model downloaded and cached successfully!")
    print("=" * 60)


# GPU configuration - using new Modal 1.0 syntax
GPU_CONFIG = "A100-40GB"

# Container settings
SCALEDOWN_WINDOW = 60 * 10  # Keep warm for 10 minutes


# NOTE: vLLM server commented out because vLLM 0.6.6 does NOT support
# Qwen2_5_VLForConditionalGeneration (the architecture UI-TARS uses).
# vLLM only supports Qwen2VLForConditionalGeneration (older Qwen2-VL).
# Use the Transformers implementation below instead.
#
# @app.function(
#     image=vllm_image,
#     gpu=GPU_CONFIG,
#     volumes={"/model_cache": model_cache},
#     timeout=60 * 20,
#     scaledown_window=SCALEDOWN_WINDOW,
# )
# @modal.concurrent(max_inputs=100)
# @modal.web_server(port=8000, startup_timeout=180)
# def serve():
#     """vLLM server - NOT SUPPORTED for UI-TARS (Qwen2.5-VL architecture)"""
#     pass


# Alternative: Custom implementation with transformers (if vLLM doesn't work)
@app.cls(
    image=vllm_image,
    gpu=GPU_CONFIG,
    volumes={"/model_cache": model_cache},
    timeout=60 * 20,
    scaledown_window=SCALEDOWN_WINDOW,
    # Secret optional - only needed for gated models
    # secrets=[modal.Secret.from_name("huggingface-secret")],
)
@modal.concurrent(max_inputs=100)
class UITARSTransformersServer:
    """
    Fallback implementation using HuggingFace Transformers.
    Use this if vLLM doesn't fully support UI-TARS vision features yet.
    
    Deploy with: modal deploy deploy_uitars_modal.py::UITARSTransformersServer.chat_completions
    """
    
    @modal.enter()
    def load_model(self):
        """Load the UI-TARS model on container startup."""
        import torch
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

        print("=" * 60)
        print("🚀 Initializing UI-TARS-1.5-7B (Transformers)")
        print("=" * 60)
        print(f"📦 Model: {MODEL_NAME}")
        print(f"🎮 GPU: A100 40GB")
        print()

        # Detect device
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
            print("🎮 Using CUDA GPU")
        else:
            self.device = torch.device("cpu")
            print("💻 Using CPU")

        # Load processor for text and image processing
        print("🔄 Loading processor...")
        self.processor = AutoProcessor.from_pretrained(
            MODEL_NAME,
            cache_dir="/model_cache",
            trust_remote_code=True,
        )

        # Load model - MUST use Qwen2_5_VLForConditionalGeneration for generation
        # AutoModel loads Qwen2_5_VLModel which doesn't have .generate() method
        print("🔄 Loading model...")
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            MODEL_NAME,
            cache_dir="/model_cache",
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        self.model.eval()

        print("✅ Model loaded successfully!")
        print()
    
    @modal.method()
    def generate(self, image_base64: str, query: str, max_tokens: int = 100) -> str:
        """
        Generate response from UI-TARS model using proper Qwen2.5-VL format.

        Args:
            image_base64: Base64-encoded image
            query: Text query
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response (coordinates)
        """
        import torch
        import base64
        import io
        from PIL import Image

        # Decode base64 image
        if "base64," in image_base64:
            image_base64 = image_base64.split("base64,")[1]
        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes))

        # Run inference using proper Qwen2.5-VL format
        with torch.no_grad():
            # Prepare messages in Qwen2.5-VL format
            # The model expects a conversation format with image and text
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": query},
                    ],
                }
            ]

            # Process inputs using the processor's apply_chat_template
            # This handles both text tokenization and image processing
            inputs = self.processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt"
            ).to(self.model.device)

            # Generate response
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
            )

            # Trim the input tokens from the output
            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]

            # Decode response
            response = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

        return response
    
    @modal.asgi_app()
    def fastapi_app(self):
        """
        Create a FastAPI app with OpenAI-compatible endpoints.
        This allows us to have proper /v1/chat/completions path.
        """
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.responses import JSONResponse
        import time
        
        web_app = FastAPI(title="UI-TARS Grounding Server")
        
        # Store reference to generate method to avoid Modal Function name conflict
        generate_fn = self.generate.local
        
        @web_app.get("/health")
        async def health():
            """Health check endpoint."""
            return {"status": "ok", "model": "ui-tars-1.5-7b"}
        
        @web_app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            """
            OpenAI-compatible chat completions endpoint.
            
            Usage:
                curl -X POST https://your-workspace--uitars-transformers.modal.run/v1/chat/completions \
                    -H "Content-Type: application/json" \
                    -d '{"messages": [{"role": "user", "content": [...]}]}'
            """
            try:
                data = await request.json()
                messages = data.get("messages", [])
                max_tokens = data.get("max_tokens", 100)
                
                # Extract image and text
                image_base64 = None
                query = ""
                
                for message in messages:
                    if message.get("role") == "user":
                        content = message.get("content", [])
                        if isinstance(content, list):
                            for item in content:
                                if item.get("type") == "image_url":
                                    image_base64 = item.get("image_url", {}).get("url", "")
                                elif item.get("type") == "text":
                                    query = item.get("text", "")
                        elif isinstance(content, str):
                            query = content
                
                if not image_base64 or not query:
                    raise HTTPException(status_code=400, detail="Missing image or query")
                
                # Generate response using the local method reference
                start_time = time.time()
                response_text = generate_fn(image_base64, query, max_tokens)
                inference_time = time.time() - start_time
                
                print(f"✅ Inference completed in {inference_time:.2f}s")
                
                # Return OpenAI-compatible response
                return JSONResponse({
                    "id": f"chatcmpl-uitars-{int(time.time())}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "ui-tars-1.5-7b",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": response_text
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    }
                })
                
            except HTTPException:
                raise
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=str(e))
        
        return web_app


@app.local_entrypoint()
def main():
    """
    Modal deployment helper.
    
    This function provides deployment instructions.
    """
    print("=" * 60)
    print("🚀 UI-TARS Modal Deployment Guide")
    print("=" * 60)
    print()
    print("⚠️  IMPORTANT: vLLM NOT SUPPORTED")
    print("────────────────────────────────────────────────────────")
    print("  vLLM 0.6.6 does NOT support Qwen2.5-VL architecture.")
    print("  UI-TARS-1.5-7B is based on Qwen2.5-VL (Qwen2_5_VLForConditionalGeneration).")
    print("  vLLM only supports older Qwen2-VL (Qwen2VLForConditionalGeneration).")
    print()
    print("  ✅ You MUST use the Transformers endpoint instead.")
    print()
    print()
    print("STEP 1: Download Model to Modal Volume (one-time setup)")
    print("────────────────────────────────────────────────────────")
    print("  modal run deploy_uitars_modal.py::download_model")
    print()
    print("  This downloads the 31GB model to persistent storage.")
    print("  You only need to do this once.")
    print()
    print()
    print("STEP 2: Deploy the Transformers Server")
    print("────────────────────────────────────────────────────────")
    print("  modal deploy deploy_uitars_modal.py")
    print()
    print("  This deploys the HuggingFace Transformers server.")
    print("  You'll get a URL like:")
    print("  https://your-workspace--uitars-transformers.modal.run")
    print()
    print()
    print("STEP 3: Test Your Deployment")
    print("────────────────────────────────────────────────────────")
    print("  python test_modal_uitars.py <your-modal-url>")
    print()
    print("  Example:")
    print("  python test_modal_uitars.py \\")
    print("    https://myworkspace--uitars-transformers.modal.run")
    print()
    print()
    print("STEP 4: Use with Agent S3")
    print("────────────────────────────────────────────────────────")
    print("  agent_s \\")
    print("    --provider openai \\")
    print("    --model gpt-5-2025-08-07 \\")
    print("    --ground_provider huggingface \\")
    print("    --ground_url <your-modal-url> \\")
    print("    --ground_model ui-tars-1.5-7b \\")
    print("    --grounding_width 1920 \\")
    print("    --grounding_height 1080")
    print()
    print()
    print("=" * 60)
    print("📚 Documentation")
    print("=" * 60)
    print()
    print("  Modal Dashboard:  https://modal.com/apps")
    print("  Modal Docs:       https://modal.com/docs")
    print("  Transformers:     https://huggingface.co/docs/transformers")
    print()
    print("=" * 60)
    print()
    print("💡 The Transformers server exposes OpenAI-compatible API at:")
    print("   <your-modal-url>/v1/chat/completions")
    print()
    print("=" * 60)
