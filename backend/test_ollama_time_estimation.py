"""
Test assignment time estimation with Ollama integration.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.time_estimator import estimate_assignment_time


async def test_time_estimation():
    """Test time estimation with a sample assignment."""
    test_assignment = """
    Assignment: Data Structures and Algorithms
    
    Complete the following problems:
    1. Implement a binary search tree with insert, delete, and search operations
    2. Write a function to find the maximum depth of a binary tree
    3. Implement merge sort algorithm
    4. Solve the coin change problem using dynamic programming
    5. Explain the time and space complexity of each solution
    
    Submit your code with comments and test cases.
    """
    
    print("Testing assignment time estimation with Ollama...")
    print("=" * 60)
    print(f"Assignment text:\n{test_assignment}\n")
    print("=" * 60)
    
    result = await estimate_assignment_time(test_assignment, "programming")
    
    print("\nEstimation Result:")
    print("=" * 60)
    for key, value in result.items():
        print(f"{key}: {value}")
    print("=" * 60)
    
    provider = result.get("analysis_provider", "unknown")
    if provider == "ollama":
        print("\n✅ SUCCESS: Time estimation used Ollama AI")
    elif provider == "heuristic":
        print("\n⚠️  WARNING: Fell back to heuristic estimator (Ollama may not be configured)")
    else:
        print(f"\n❓ UNKNOWN: Provider is {provider}")


if __name__ == "__main__":
    asyncio.run(test_time_estimation())
