import asyncio
import os
import sys
import logging
import json

# Add parent dir to path
sys.path.append(os.path.abspath("."))

from app.services.ollama_timetable_extractor import OllamaTimetableExtractor

async def run_diagnostics():
    logging.basicConfig(level=logging.INFO)
    extractor = OllamaTimetableExtractor()
    samples_dir = "tests/samples"
    
    samples = [
        "light_grid.png",
        "light_lifestyle.png",
        "dark_grid_1.png",
        "dark_grid_2.png"
    ]
    
    results = {}
    
    for sample in samples:
        path = os.path.join(samples_dir, sample)
        if not os.path.exists(path):
            print(f"Skipping {sample}, not found.")
            continue
            
        print(f"\n>>> Extracting from: {sample} ...")
        try:
            # We skip the high-level extract_from_file and go straight to vision for detailed debug
            entries = await extractor._extract_vision_two_pass(path)
            results[sample] = {
                "count": len(entries),
                "entries": entries
            }
            print(f"    Result: {len(entries)} entries found.")
        except Exception as e:
            print(f"    Failed: {str(e)}")
            results[sample] = {"error": str(e)}

    # Save summary
    with open("diagnostic_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSummary saved to diagnostic_results.json")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
