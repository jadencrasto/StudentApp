import asyncio
import logging
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.abspath("."))

from app.services.ollama_timetable_extractor import OllamaTimetableExtractor

async def test_image():
    logging.basicConfig(level=logging.INFO)
    extractor = OllamaTimetableExtractor()
    
    img_path = r"C:\Users\jason\.gemini\antigravity\brain\b29d0cab-5484-4e24-bf27-2cc3f7ad8213\media__1773418397878.png"
    if not os.path.exists(img_path):
        print(f"Image not found at {img_path}")
        return

    print(f"--- Testing Image: {img_path} ---")
    
    # Run Path 1 (Vision) specifically to see raw AI output
    try:
        image = extractor._load_image(img_path, ".png")
        image = extractor._preprocess_image_for_vision(image)
        import io, base64, httpx
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        print("\n--- Calling Ollama Directly ---")
        async with httpx.AsyncClient(timeout=600.0) as http:
            # Import prompt from the extractor module
            import app.services.ollama_timetable_extractor as ote
            resp = await http.post(
                f"http://localhost:11434/api/generate",
                json={
                    "model": extractor.vision_model,
                    "prompt": ote.EXTRACTION_PROMPT,
                    "images": [image_base64],
                    "stream": False,
                    "options": {"temperature": 0.1},
                }
            )
            raw_response = resp.json().get("response", "")
            print("\n--- RAW AI RESPONSE ---")
            print(raw_response)
            
            parsed = extractor._parse_json(raw_response)
            print("\n--- PARSED ENTRIES (BEFORE POST-PROCESS) ---")
            print(json.dumps(parsed, indent=2))
            
            processed = extractor._post_process_entries(parsed if isinstance(parsed, list) else parsed.get("entries", []))
            print("\n--- PROCESSED ENTRIES ---")
            print(json.dumps(processed, indent=2))
            
    except Exception as e:
        print(f"Direct test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_image())
