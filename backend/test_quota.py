import os
import asyncio
from google import genai
import settings as settings_mod

async def test_models():
    api_key_str = await settings_mod.get_setting("llm_api_key")
    if not api_key_str:
        print("No API key found in DB.")
        return
        
    client = genai.Client(api_key=api_key_str)
    
    print("Testing gemini-2.5-flash...")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Hello, does this model have any quota left?'
        )
        print("SUCCESS with gemini-2.5-flash!")
    except Exception as e:
        print("FAILED with gemini-2.5-flash:", e)

    print("\nTesting gemini-1.5-flash...")
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents='Hello, does this model have any quota left?'
        )
        print("SUCCESS with gemini-1.5-flash!")
    except Exception as e:
        print("FAILED with gemini-1.5-flash:", e)

if __name__ == "__main__":
    asyncio.run(test_models())
