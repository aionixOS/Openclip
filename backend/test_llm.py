import asyncio
import llm
import settings as settings_mod

async def test():
    await settings_mod.set_setting('llm_model', 'gemini-flash-lite-latest')
    
    transcript = [
        {"start": 10.0, "end": 25.0, "text": "This is a great moment in the video where we talk about AI."},
        {"start": 30.0, "end": 50.0, "text": "And here is another amazing insight that could go viral."},
        {"start": 60.0, "end": 80.0, "text": "Finally, we conclude with a funny joke that everyone loves."}
    ]
    
    api_key = await settings_mod.get_setting('llm_api_key')
    
    try:
        results = await llm.get_clip_suggestions(
            transcript,
            provider='gemini',
            api_key=api_key,
            model='gemini-flash-lite-latest',
            video_duration=100.0
        )
        print("FINAL RESULTS:")
        for r in results:
            print(f"- {r}")
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(test())
