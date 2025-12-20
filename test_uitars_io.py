#!/usr/bin/env python3
"""
Simple script to understand UI-TARS model Input/Output format.

UI-TARS (UI Grounding Model) takes an image + text query and returns
coordinates for UI elements. It uses OpenAI-compatible API format.

Usage:
    python test_uitars_io.py
"""

import base64
import json
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


# Your Modal endpoint URL
UITARS_URL = "https://aryankeluskar--uitars-grounding-server-uitarstransformer-03ccf2.modal.run"


def create_test_image():
    """
    Create a simple test image with UI elements.

    Returns:
        str: Base64-encoded image
    """
    # Create a 800x600 image (simulating a UI screenshot)
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)

    # Draw some UI elements
    # Header bar
    draw.rectangle([0, 0, 800, 60], fill='#2196F3')
    draw.text((20, 20), "My Application", fill='white', font=None)

    # Login button
    draw.rectangle([300, 250, 500, 310], fill='#4CAF50', outline='black', width=2)
    draw.text((360, 270), "Login Button", fill='white', font=None)

    # Search box
    draw.rectangle([200, 150, 600, 200], fill='white', outline='gray', width=2)
    draw.text((210, 165), "Search...", fill='gray', font=None)

    # Convert to base64
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_bytes = buffer.getvalue()
    base64_image = base64.b64encode(img_bytes).decode('utf-8')

    return base64_image


def test_uitars_model(query="Click on the login button"):
    """
    Test the UI-TARS model with a sample query.

    Args:
        query: The grounding query (e.g., "Click on the login button")

    Returns:
        dict: Response from the model
    """
    print("=" * 70)
    print("🧪 UI-TARS Model Input/Output Test")
    print("=" * 70)
    print()

    # Step 1: Create test image
    print("📸 Step 1: Creating test image...")
    base64_image = create_test_image()
    print(f"   ✅ Image created (size: {len(base64_image)} chars in base64)")
    print()

    # Step 2: Prepare the request payload
    print("📝 Step 2: Preparing request payload...")
    print()
    print("   INPUT FORMAT:")
    print("   " + "-" * 66)

    # This is the OpenAI-compatible format the model expects
    payload = {
        "model": "ui-tars-1.5-7b",  # Model name (optional)
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": query
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 100  # Optional: max tokens to generate
    }

    # Print the structure (without full base64 for readability)
    payload_display = {
        "model": payload["model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,<{len(base64_image)} chars>"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 100
    }

    print(json.dumps(payload_display, indent=2))
    print()

    # Step 3: Send request
    print("📤 Step 3: Sending request to UI-TARS endpoint...")
    print(f"   URL: {UITARS_URL}/v1/chat/completions")
    print(f"   Query: \"{query}\"")
    print()

    try:
        response = requests.post(
            f"{UITARS_URL}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

        # Step 4: Display response
        print("✅ Step 4: Response received!")
        print()
        print("   OUTPUT FORMAT:")
        print("   " + "-" * 66)
        print(json.dumps(result, indent=2))
        print()

        # Extract and explain the coordinates
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            print("   📍 EXTRACTED COORDINATES:")
            print("   " + "-" * 66)
            print(f"   {content}")
            print()
            print("   💡 EXPLANATION:")
            print("   These coordinates represent the location of the UI element")
            print("   in the format expected by the grounding model.")
            print("   Format typically: [x1, y1, x2, y2] or similar")

        return result

    except requests.exceptions.RequestException as e:
        print(f"❌ Error: Request failed!")
        print(f"   {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Status: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
        return None

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main function with multiple test examples."""
    print("\n" + "=" * 70)
    print("🚀 UI-TARS Model Input/Output Explorer")
    print("=" * 70)
    print()
    print("This script demonstrates:")
    print("  1. How to prepare image input (base64 encoding)")
    print("  2. The expected OpenAI-compatible request format")
    print("  3. The response format with grounding coordinates")
    print()

    # Test queries
    test_queries = [
        "Click on the login button",
        # Uncomment to test more queries:
        # "Click on the search box",
        # "Find the header",
    ]

    for i, query in enumerate(test_queries, 1):
        if i > 1:
            print("\n" + "=" * 70)
            print(f"Test {i}/{len(test_queries)}")
            print("=" * 70)
            print()

        result = test_uitars_model(query)

        if result:
            print()
            print("=" * 70)
            print("✅ TEST PASSED")
            print("=" * 70)
        else:
            print()
            print("=" * 70)
            print("❌ TEST FAILED")
            print("=" * 70)
            break

    print()
    print("=" * 70)
    print("📚 Quick Reference")
    print("=" * 70)
    print()
    print("INPUT:")
    print("  - Endpoint: <url>/v1/chat/completions")
    print("  - Method: POST")
    print("  - Content-Type: application/json")
    print("  - Body:")
    print("    {")
    print('      "messages": [')
    print("        {")
    print('          "role": "user",')
    print('          "content": [')
    print('            {"type": "text", "text": "your query"},')
    print('            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}')
    print("          ]")
    print("        }")
    print("      ],")
    print('      "max_tokens": 100')
    print("    }")
    print()
    print("OUTPUT:")
    print("  - OpenAI-compatible chat completion format")
    print("  - Coordinates in choices[0].message.content")
    print("  - Format depends on the grounding model's training")
    print()
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
