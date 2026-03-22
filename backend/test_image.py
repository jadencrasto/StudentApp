import asyncio
import os
import sys

from app.services.ollama_timetable_extractor import OllamaTimetableExtractor

async def run_test(file_path: str):
    print(f"\n==============================================")
    print(f"Testing image: {file_path}")
    print(f"==============================================\n")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    extractor = OllamaTimetableExtractor()
    
    # Run the full pipeline
    result = await extractor.extract_from_file(file_path)
    
    print("\n[RESULT]")
    print(f"Status:     {result['status']}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Method:     {result.get('notes', 'Unknown')}")
    
    entries = result.get('entries', [])
    print(f"\nExtracted:  {len(entries)} entries")
    
    # Group by day for easier reading
    days = {}
    for e in entries:
        day = e.get('day_of_week')
        if day not in days:
            days[day] = []
        days[day].append(e)
        
    # Print sorted
    day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
    for d in sorted(days.keys()):
        print(f"\nDay {d} ({day_names.get(d, 'Unknown')}): {len(days[d])} classes")
        for e in sorted(days[d], key=lambda x: x['start_time']):
            print(f"  {e['start_time']} - {e['end_time']} | {e['subject']}")
            
    if result['status'] == 'failed':
        print(f"\nError: {result.get('error')}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_image.py <path_to_image>")
        sys.exit(1)
        
    asyncio.run(run_test(sys.argv[1]))
