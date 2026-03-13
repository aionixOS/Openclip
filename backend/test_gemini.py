"""Test script for Gemini API"""
import time
import asyncio
import sys
sys.path.insert(0, '.')

import settings as settings_mod

async def test():
    print("=" * 50)
    print("GEMINI API TEST")
    print("=" * 50)

    # Get decrypted API key
    api_key = await settings_mod.get_setting('llm_api_key')
    model = await settings_mod.get_setting('llm_model')

    print(f"Model: {model}")
    print(f"API Key (first 15 chars): {api_key[:15] if api_key else 'None'}...")
    print(f"API Key length: {len(api_key) if api_key else 0}")

    if not api_key or api_key == '<decryption failed>':
        print("ERROR: API key decryption failed!")
        return

    from google import genai
    from google.genai import types

    print(f"\nSending test request to {model}...")
    print("(Pro models can take 30-60+ seconds)")

    client = genai.Client(
        api_key=api_key,
        http_options={"timeout": 120000}  # 120 second timeout
    )

    start = time.time()
    try:
        response = client.models.generate_content(
            model=model,
            contents='Return a simple JSON array: [{"status": "ok"}]',
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )
        elapsed = time.time() - start
        print(f"\n✓ SUCCESS! Response received in {elapsed:.1f} seconds")
        print(f"Response: {response.text[:200] if response.text else 'Empty response'}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n✗ ERROR after {elapsed:.1f} seconds")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")

if __name__ == "__main__":
    asyncio.run(test())
