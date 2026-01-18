import sys
import base64
import requests
import json
import re
from PIL import Image, ImageDraw

def overlay_points(image_path, points, output_path="output_overlay.png"):
    """
    Overlay red dots on the image at the specified coordinates.
    """
    try:
        with Image.open(image_path) as img:
            draw = ImageDraw.Draw(img)
            radius = 20  # 3px radius (will create a 6px diameter dot, closer to "3px point")
            
            for point in points:
                x = point.get('x') or point.get('X')
                y = point.get('y') or point.get('Y')
                
                if x is not None and y is not None:
                    # Draw a red circle
                    # Coordinates are center, so we calculate bounding box
                    left_up_point = (x - radius, y - radius)
                    right_down_point = (x + radius, y + radius)
                    draw.ellipse([left_up_point, right_down_point], fill="red", outline="red")
            
            img.save(output_path)
            print(f"Overlay image saved to: {output_path}")
            
    except Exception as e:
        print(f"Error creating overlay: {e}")

def main():
    DEFAULT_MODAL_URL = "https://aryankeluskar--uitars-grounding-server-uitarstransformer-03ccf2.modal.run"
    
    if len(sys.argv) < 2:
        print("Usage: python test_uitars_simple.py <image_path> [modal_url] [user_prompt] [system_prompt]")
        print(f"Default modal_url: {DEFAULT_MODAL_URL}")
        sys.exit(1)

    image_path = sys.argv[1]
    
    # Handle optional arguments with defaults
    modal_url = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else DEFAULT_MODAL_URL
    user_prompt = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "Describe the UI elements in this image."
    system_prompt = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else (
        "You are a UI automation assistant. "
        "Return a minimal JSON response containing only the X and Y coordinates of all elements that match the user's request. "
        "Output ONLY valid JSON. "
        "Format: [{\"x\": 123, \"y\": 456}, ...]"
    )

    # Fix URL formatting - ensure it points to the chat completions endpoint
    if not modal_url.endswith("/v1/chat/completions"):
        modal_url = modal_url.rstrip("/")
        if not modal_url.endswith("/v1"):
            modal_url += "/v1"
        modal_url += "/chat/completions"

    print(f"Reading image from {image_path}...")
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Error reading image: {e}")
        sys.exit(1)

    # UI-TARS expects an OpenAI-compatible format with image_url
    messages = []
    
    # Add system prompt if provided (though some VLM endpoints might ignore it or prefer it in user prompt)
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{encoded_string}"
                }
            },
            {
                "type": "text",
                "text": user_prompt
            }
        ]
    })

    payload = {
        "model": "ui-tars-1.5-7b",  # Model name is often ignored by the server but good to include
        "messages": messages,
        "max_tokens": 512,
        "temperature": 0.0
    }

    headers = {
        "Content-Type": "application/json",
        # Some Modal endpoints might check for a token presence even if public
        "Authorization": "Bearer modal-endpoint-no-auth-required" 
    }

    print(f"Sending request to {modal_url}...")
    try:
        response = requests.post(modal_url, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print("\nResponse:")
            # Extract the actual content from the OpenAI-style response
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            print("-" * 40)
            print(content)
            print("-" * 40)
            
            # Try to parse JSON or coordinate format and overlay points
            try:
                # Clean up content if it contains markdown code blocks
                clean_content = content.strip()
                if clean_content.startswith("```json"):
                    clean_content = clean_content[7:]
                if clean_content.startswith("```"):
                    clean_content = clean_content[3:]
                if clean_content.endswith("```"):
                    clean_content = clean_content[:-3]
                
                points = []
                # First try parsing as JSON
                try:
                    parsed = json.loads(clean_content)
                    if isinstance(parsed, list):
                        points = parsed
                except json.JSONDecodeError:
                    # If JSON fails, try regex for (x,y) format
                    # UI-TARS often outputs coordinates like (123,456)
                    matches = re.findall(r'\((\d+),\s*(\d+)\)', content)
                    if matches:
                        points = [{"x": int(x), "y": int(y)} for x, y in matches]
                        print(f"Found {len(points)} coordinate pairs via regex.")

                if points:
                    overlay_points(image_path, points)
                else:
                    print("Could not parse response as JSON or (x,y) coordinates, skipping overlay.")

            except Exception as e:
                print(f"Error processing overlay: {e}")

            print("\nFull JSON:")
            print(json.dumps(result, indent=2))
        else:
            print(f"Error {response.status_code}:")
            print(response.text)
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()

