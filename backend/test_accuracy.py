import asyncio
import os
import sys
import json
import logging

# Configure logging to see breadcrumbs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.ollama_timetable_extractor import OllamaTimetableExtractor

async def run_test(img_path, label):
    print(f"\n--- Testing: {label} ---")
    print(f"Path: {img_path}")
    
    extractor = OllamaTimetableExtractor()
    models = await extractor._available_models()
    print(f"Available models: {models}")
    try:
        result = await extractor.extract_from_file(img_path)
        print(f"Status: {result.get('status')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Notes: {result.get('notes')}")
        entries = result.get("entries", [])
        print(f"Found {len(entries)} entries.")
        
        # Print first 5 and last 5 to check coverage
        if entries:
            print("First 3 entries:")
            for e in entries[:3]:
                print(f"  {e['day_of_week']} {e['start_time']}-{e['end_time']}: {e['subject']}")
            print("Last 3 entries:")
            for e in entries[-3:]:
                print(f"  {e['day_of_week']} {e['start_time']}-{e['end_time']}: {e['subject']}")
                
        # Check for headers in subjects
        headers_found = [e['subject'] for e in entries if "Weekly" in e['subject'] or "School" in e['subject'] or "Timetable" in e['subject']]
        if headers_found:
            print(f"WARNING: Potential headers found as subjects: {headers_found}")
        else:
            print("SUCCESS: No common header words found in subjects.")
            
    except Exception as e:
        print(f"Error during extraction: {e}")

async def main():
    # Use absolute paths from artifact directory
    artifact_dir = r"C:\Users\jason\.gemini\antigravity\brain\b29d0cab-5484-4e24-bf27-2cc3f7ad8213"
    
    images = [
        ("media__1773415672687.png", "Weekly School (Horizontal)"),
        ("media__1773416697860.png", "ICSE Class 10 (Merged Cells)"),
    ]
    
    for img_file, label in images:
        full_path = os.path.join(artifact_dir, img_file)
        if os.path.exists(full_path):
            await run_test(full_path, label)
        else:
            print(f"Skipping {label}: File not found at {full_path}")

if __name__ == "__main__":
    asyncio.run(main())
