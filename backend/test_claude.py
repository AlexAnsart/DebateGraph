"""Test Claude API with different model names to find the correct one."""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import anthropic

client = anthropic.Anthropic()

models_to_try = [
    "claude-haiku-4-5",  # primary
    "claude-3-5-haiku-latest",
    "claude-3-haiku-20240307",
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-latest",
]

for model_name in models_to_try:
    try:
        response = client.messages.create(
            model=model_name,
            max_tokens=10,
            messages=[{"role": "user", "content": "Say hi"}],
        )
        print(f"SUCCESS: {model_name} -> {response.model} -> {response.content[0].text}")
    except Exception as e:
        print(f"FAIL:    {model_name} -> {type(e).__name__}: {str(e)[:100]}")
