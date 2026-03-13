import time
from google import genai
from google.genai import types

api_key = 'AIzaSyDSmfA5aquYs1hGwpa_ZZ-2sSwhRIAkB_w'
model = 'gemini-2.5-flash'

print(f'Testing: {model}')
client = genai.Client(api_key=api_key, http_options={'timeout': 60000})

start = time.time()
try:
    response = client.models.generate_content(
        model=model,
        contents='Return JSON: [{"test": true}]',
        config=types.GenerateContentConfig(temperature=0.3, response_mime_type='application/json'),
    )
    elapsed = time.time() - start
    print(f'SUCCESS in {elapsed:.1f}s: {response.text}')
except Exception as e:
    elapsed = time.time() - start
    print(f'ERROR after {elapsed:.1f}s: {e}')
