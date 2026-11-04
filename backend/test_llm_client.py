"""
Run this file directly to check your NVIDIA NIM API key actually works,
before we build any real agent on top of it.

Usage:
    python test_llm_client.py
"""

from agents.llm_client import LLMClient

def main():
    print("Testing LLMClient with a cheap, fast model (push_intent)...")
    client = LLMClient(agent_name="push_intent")

    answer = client.generate(
        system_prompt="You are a helpful assistant. Answer in one short sentence.",
        user_prompt="What is the capital of France?",
    )

    print("\n--- Response from the model ---")
    print(answer)
    print("--------------------------------\n")
    print("If you see a real answer above, your setup works correctly.")


if __name__ == "__main__":
    main()
