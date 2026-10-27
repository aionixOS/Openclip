"""
llm.py — Multi-provider LLM integration for clip suggestion (v4.0 Map-Reduce).
"""

import json
import re
import logging
import asyncio
import random
from typing import Optional, Callable

import httpx  # type: ignore
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

_TIMEOUT = 120.0

# Rate limit tracking - stores the last retry-after value
_last_retry_after: float = 0.0

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_clip_suggestions(
    transcript: list[dict],
    provider: str,
    api_key: str,
    model: str,
    video_duration: float,
    progress_callback: Optional[Callable[[str, float, str], None]] = None
) -> list[dict]:
    """
    Map-Reduce approach to stay under TPM limits.
    
    Phase 1 (Map): Split transcript into chunks,
                   find candidates in each chunk
    Phase 2 (Reduce): Rank all candidates,
                      return final top 5-10 clips
    """
    if not transcript:
        logger.warning("Empty transcript — skipping LLM call")
        return []

    def progress(stage: str, pct: float, msg: str):
        if progress_callback:
            progress_callback(stage, pct, msg)
        else:
            logger.info(f"Progress: [{stage}] {pct}% - {msg}")

    # Step 1 — Split into chunks of max 8 minutes each (larger chunks = fewer API calls)
    chunks = _chunk_transcript(transcript, chunk_minutes=8)

    logger.info(f"Split transcript into {len(chunks)} chunks for processing")

    # Step 2 — Get candidates from each chunk (MAP)
    all_candidates = []
    for i, chunk in enumerate(chunks):
        progress(
            "analyzing",
            55 + (i / len(chunks) * 15),
            f"Analyzing part {i+1} of {len(chunks)}..."
        )
        candidates = await _analyze_chunk(chunk, i, len(chunks), provider, api_key, model)
        all_candidates.extend(candidates)

        # Add delay between chunks to avoid rate limits (skip delay on last chunk)
        # Use 4-6 second delay with jitter to stay well under 50 RPM limit
        if i < len(chunks) - 1:
            base_delay = 4.0
            jitter = random.uniform(0, 2.0)  # Add 0-2s random jitter
            delay_seconds = base_delay + jitter
            logger.info(f"Rate limit protection: waiting {delay_seconds:.1f}s before next chunk...")
            await asyncio.sleep(delay_seconds)

    # Step 3 — If only 1 chunk, candidates are already final
    if len(chunks) == 1:
        return _validate_suggestions(all_candidates, video_duration)

    # Step 4 — Rank all candidates (REDUCE)
    # Add delay before reduce step to avoid hitting rate limits
    await asyncio.sleep(random.uniform(3.0, 5.0))

    progress("analyzing", 72, "Ranking best moments...")
    final_clips = await _rank_candidates(all_candidates, video_duration, provider, api_key, model)
    progress("analyzing", 75, f"Found {len(final_clips)} clips")

    return _validate_suggestions(final_clips, video_duration)


def _chunk_transcript(
    transcript: list[dict],
    chunk_minutes: int = 3
) -> list[list[dict]]:
    """
    Split transcript segments into chunks of N minutes.
    """
    chunk_seconds = chunk_minutes * 60
    overlap = 15  # seconds
    chunks = []
    start = 0.0
    
    while start < transcript[-1]["end"]:
        end = start + chunk_seconds + overlap
        chunk = [
            seg for seg in transcript
            if seg["start"] >= start and seg["start"] < end
        ]
        if chunk:
            chunks.append(chunk)
        start += chunk_seconds  # next chunk starts without overlap
        
    return chunks


async def _analyze_chunk(
    chunk: list[dict],
    chunk_index: int,
    total_chunks: int,
    provider: str,
    api_key: str,
    model: str
) -> list[dict]:
    """
    Send ONE chunk to LLM. Stay under 1500 tokens.
    """
    prompt = _build_chunk_prompt(chunk, chunk_index, total_chunks)
    raw = await _call_provider_with_retry(provider, api_key, model, prompt)
    logger.info(f"LLM raw response for chunk {chunk_index+1}: {raw[:500]}")
    parsed = _parse_llm_json(raw)
    logger.info(f"Parsed {len(parsed)} clips from chunk {chunk_index+1}")
    return parsed


async def _rank_candidates(
    candidates: list[dict],
    video_duration: float, # passed for consistency but might not be used here
    provider: str,
    api_key: str,
    model: str
) -> list[dict]:
    """
    Final reduce step. Send ALL candidates to LLM
    and ask it to pick the best 5-10.
    """
    prompt = _build_reduce_prompt(candidates)
    raw = await _call_provider_with_retry(provider, api_key, model, prompt)
    return _parse_llm_json(raw)


def _format_transcript(segments: list[dict]) -> str:
    """
    Format segments as readable timestamped text.
    """
    lines = []
    for seg in segments:
        text = seg['text'].strip()
        if not text:
            continue
        start_m = int(seg['start'] // 60)
        start_s = int(seg['start'] % 60)
        end_m = int(seg['end'] // 60)
        end_s = int(seg['end'] % 60)
        lines.append(f"[{start_m:02d}:{start_s:02d}-{end_m:02d}:{end_s:02d}] {text}")
    return "\n".join(lines)


def _format_candidates(candidates: list[dict]) -> str:
    """
    Format candidates list as compact text for reduce step.
    """
    lines = []
    for i, c in enumerate(candidates):
        start_m = int(c['start'] // 60)
        start_s = int(c['start'] % 60)
        end_m = int(c['end'] // 60)
        end_s = int(c['end'] % 60)
        lines.append(f"{i+1}. [{start_m:02d}:{start_s:02d}-{end_m:02d}:{end_s:02d}] \"{c.get('title','')}\" score:{c.get('viral_score',0)} | {c.get('reason','')}")
    return "\n".join(lines)


def _validate_suggestions(
    suggestions: list[dict],
    video_duration: float
) -> list[dict]:
    """
    Final validation pass on all suggestions.
    Tries strict 60-80s first; if nothing survives, falls back to lenient (15s+).
    """
    logger.info(f"RAW LLM SUGGESTIONS RECEIVED FOR VALIDATION ({len(suggestions)} clips): {suggestions}")

    if not suggestions:
        logger.warning("No suggestions received from LLM at all")
        return []

    # --- First pass: strict 60-80s ---
    strict = _filter_suggestions(suggestions, video_duration, min_dur=45, target_min=60, target_max=80)

    if strict:
        logger.info(f"Strict validation kept {len(strict)} clips")
        return strict

    # --- Fallback: lenient, accept anything 15s+ and extend short ones to 60s ---
    logger.warning("Strict 60-80s validation returned 0 clips — falling back to lenient mode")
    lenient = _filter_suggestions(suggestions, video_duration, min_dur=15, target_min=60, target_max=90)

    if lenient:
        logger.info(f"Lenient validation kept {len(lenient)} clips")
    else:
        logger.warning("No valid clips survived even lenient validation")

    return lenient


def _filter_suggestions(
    suggestions: list[dict],
    video_duration: float,
    min_dur: float,
    target_min: float,
    target_max: float,
) -> list[dict]:
    """
    Filter and adjust clip suggestions within duration bounds.
    Returns non-overlapping clips sorted by start time.
    """
    import copy
    valid = []
    for s in suggestions:
        s = copy.deepcopy(s)  # don't mutate originals (needed for fallback)

        # Swap if start > end
        if s["start"] > s["end"]:
            s["start"], s["end"] = s["end"], s["start"]

        # Clamp to valid bounds
        s["start"] = max(0, s["start"])
        s["end"] = min(s["end"], video_duration)

        if s["start"] >= s["end"]:
            continue

        dur = s["end"] - s["start"]

        if dur < min_dur:
            logger.warning(f"Dropping clip - too short ({dur:.1f}s < {min_dur}s): {s.get('title')}")
            continue
        if dur < target_min:
            # Try to extend
            s["end"] = min(s["start"] + target_min, video_duration)
            dur = s["end"] - s["start"]
            logger.info(f"Extended short clip to {dur:.1f}s: {s.get('title')}")
        if dur > target_max:
            s["end"] = s["start"] + target_max
            dur = target_max
            logger.info(f"Trimmed long clip to {target_max}s: {s.get('title')}")

        valid.append(s)

    valid.sort(key=lambda x: x["start"])

    # Remove overlaps
    non_overlapping = []
    last_end = -1.0
    for s in valid:
        if s["start"] >= last_end:
            non_overlapping.append(s)
            last_end = s["end"]

    return non_overlapping


def _build_chunk_prompt(chunk: list[dict], chunk_index: int, total_chunks: int) -> str:
    # Get the time bounds of this chunk
    chunk_start = chunk[0]["start"] if chunk else 0
    chunk_end = chunk[-1]["end"] if chunk else 0

    return f"""You are an expert viral video editor and content creator for social media platforms (YouTube Shorts, TikTok, Instagram Reels) targeting Indonesian audiences.
This is part {chunk_index+1} of {total_chunks} of a YouTube video transcript.
This section covers timestamps from {chunk_start:.0f}s to {chunk_end:.0f}s.

Find the 3-5 BEST moments in this section suitable for viral short clips.

Rules:
- Each clip MUST be between 60 and 80 seconds long. This is STRICT — no shorter, no longer.
- Clips MUST stay within this section's bounds: {chunk_start:.0f}s to {chunk_end:.0f}s
- Must start and end at natural speech boundaries
- Only pick genuinely strong, engaging, high-retention moments
- You MUST return at least 2-3 clips for this section so we have enough options
- Make sure "start" and "end" are float numbers of seconds

ATURAN BAHASA INDONESIA (SANGAT PENTING & WAJIB):
- "title": Wajib dalam BAHASA INDONESIA. Buat judul/hook yang sangat memikat, clickbait cerdas, dan memicu rasa penasaran tinggi (maksimal 6-8 kata). Gunakan gaya bahasa viral Shorts/TikTok Indonesia (contoh: "Gak Nyangka Rahasia Ini Baru Kebongkar!", "Momen Bikin Merinding Semua Orang", "Cara Licik Otak Bikin Kita Malas").
- "reason": Wajib dalam BAHASA INDONESIA (1-2 kalimat ringkas). Tulis alasan/ringkasan menarik mengapa momen ini sangat layak ditonton dan memancing interaksi penonton.
- "hashtags": Generate 3-5 hashtag relevan dalam Bahasa Indonesia & universal (contoh: ["#shorts", "#fyp", "#faktamenarik", "#podcastindonesia", "#viral"]).
- "tags": Generate 3-5 kata kunci SEO dalam Bahasa Indonesia.

TRANSCRIPT SECTION:
{_format_transcript(chunk)}

Return ONLY JSON array:
[
  {{
    "start": <float seconds>,
    "end": <float seconds>,
    "title": "<judul viral Bahasa Indonesia, max 8 kata>",
    "reason": "<alasan/ringkasan menarik Bahasa Indonesia, 1-2 kalimat>",
    "viral_score": <1-10>,
    "hashtags": ["#tag1", "#tag2", "#tag3"],
    "tags": ["keyword1", "keyword2", "keyword3"]
  }}
]
If no strong moments found return: []"""


def _build_reduce_prompt(candidates: list[dict]) -> str:
    return f"""You are an expert viral video editor for Indonesian audiences (TikTok, YouTube Shorts, Instagram Reels).
Below are candidate clip moments found across a YouTube video.
Select the best clips for maximum viral potential.

CANDIDATES:
{_format_candidates(candidates)}

Rules:
- Return between 5 and 10 clips (each STRICTLY between 60 and 80 seconds long)
- You MUST return AT LEAST 5 clips. This is a strict requirement!
- No overlapping timestamps
- Sort by start time ascending
- "start" and "end" must be float numbers of seconds
- Adjust start/end timestamps if needed to ensure each clip is 60-80 seconds
- BAHASA INDONESIA: Pastikan "title" dan "reason" menggunakan Bahasa Indonesia yang memikat, menarik, dan siap posting!
- Keep or refine the existing title, reason, viral_score, hashtags, and tags in Bahasa Indonesia.

Return ONLY the selected candidates as JSON array in the exact same format. Do not remove any fields.
[
  {{
    "start": <float seconds>,
    "end": <float seconds>,
    "title": "<judul/hook viral Bahasa Indonesia, max 8 kata>",
    "reason": "<alasan/ringkasan menarik Bahasa Indonesia, 1-2 kalimat>",
    "viral_score": <1-10>,
    "hashtags": ["#tag1", "#tag2", "#tag3"],
    "tags": ["keyword1", "keyword2", "keyword3"]
  }}
]"""

# ---------------------------------------------------------------------------
# Provider wrappers
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Custom exception for rate limit errors with retry-after support."""
    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


def _get_retry_wait():
    """Custom wait strategy that respects retry-after header."""
    # Use random exponential backoff: min=5s, max=120s
    return wait_random_exponential(multiplier=2, min=5, max=120)


@retry(
    stop=stop_after_attempt(6),  # 6 attempts total
    wait=_get_retry_wait(),
    reraise=True
)
async def _call_provider_with_retry(provider: str, api_key: str, model: str, prompt: str) -> str:
    global _last_retry_after

    dispatch = {
        "openai": _call_openai,
        "anthropic": _call_anthropic,
        "gemini": _call_gemini,
        "ollama": _call_ollama,
    }
    handler = dispatch.get(provider)
    if handler is None:
        raise ValueError(f"Unknown LLM provider: {provider}")

    # If we recently hit a rate limit, wait the specified time before trying
    if _last_retry_after > 0:
        wait_time = _last_retry_after
        _last_retry_after = 0  # Reset after using
        logger.info(f"Respecting previous retry-after: waiting {wait_time}s...")
        await asyncio.sleep(wait_time)

    try:
        return await handler(prompt, api_key, model)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Parse retry-after header if present
            retry_after_str = e.response.headers.get("retry-after", "")
            try:
                retry_after = float(retry_after_str) if retry_after_str else 30.0
            except ValueError:
                retry_after = 30.0  # Default 30s if header is malformed

            # Add jitter to prevent thundering herd
            retry_after += random.uniform(1, 5)
            _last_retry_after = retry_after

            logger.warning(f"Rate limit hit (429). retry-after header: {retry_after_str}. Waiting {retry_after:.1f}s...")
            await asyncio.sleep(retry_after)
        raise
    except RuntimeError as e:
        # Handle Gemini rate limit and timeout errors (raised as RuntimeError)
        error_str = str(e).lower()
        if "rate limit" in error_str or "quota" in error_str:
            retry_after = 30.0 + random.uniform(5, 15)  # 35-45 seconds
            _last_retry_after = retry_after
            logger.warning(f"Gemini rate limit detected. Waiting {retry_after:.1f}s...")
            await asyncio.sleep(retry_after)
        elif "timeout" in error_str:
            # For timeouts, wait a bit less but still retry
            retry_after = 10.0 + random.uniform(2, 5)
            logger.warning(f"Gemini timeout. Waiting {retry_after:.1f}s before retry...")
            await asyncio.sleep(retry_after)
        raise


async def _call_openai(prompt: str, api_key: str, model: str) -> str:
    model = model or "gpt-4o"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _call_anthropic(prompt: str, api_key: str, model: str) -> str:
    model = model or "claude-3-5-sonnet-20241022"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def _call_gemini(prompt: str, api_key: str, model: str) -> str:
    target_model = model or "gemini-3.5-flash-lite"
    logger.info(f"Calling Gemini with model: {target_model}")

    def _do_call() -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Gemini SDK missing. Install with: pip install google-genai"
            ) from exc

        effective_api_key = api_key or ""
        if not effective_api_key:
            import os
            effective_api_key = os.environ.get("GEMINI_API_KEY", "")
        if not effective_api_key:
            raise RuntimeError("Gemini API key missing. Set it in Settings or GEMINI_API_KEY env var.")

        req_model = target_model

        # Create client with explicit timeout via http_options
        client = genai.Client(
            api_key=effective_api_key,
            http_options={"timeout": 90000}  # 90 second timeout in milliseconds
        )

        # Simplified config - no tools or thinking mode to reduce token usage
        generate_content_config = types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type="application/json",
        )

        try:
            logger.info(f"Sending prompt to Gemini ({len(prompt)} chars, model={req_model})...")
            # Use non-streaming for simpler, more reliable responses
            response = client.models.generate_content(
                model=req_model,
                contents=prompt,
                config=generate_content_config,
            )
            result = response.text or "[]"
            logger.info(f"Gemini response received ({len(result)} chars)")
            return result
        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"Gemini API error with {req_model}: {e}")
            fallback_models = [m for m in ["gemini-3.5-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash"] if m != req_model]
            if any(k in error_str for k in ["503", "404", "unavailable", "429", "resource_exhausted", "quota"]):
                for alt_model in fallback_models:
                    logger.info(f"Retrying with fallback model: {alt_model}...")
                    try:
                        response = client.models.generate_content(
                            model=alt_model,
                            contents=prompt,
                            config=generate_content_config,
                        )
                        result = response.text or "[]"
                        logger.info(f"Gemini fallback ({alt_model}) response received ({len(result)} chars)")
                        return result
                    except Exception as e2:
                        logger.error(f"Fallback {alt_model} failed: {e2}")
            if "429" in error_str or "resource_exhausted" in error_str or "quota" in error_str or "503" in error_str:
                logger.warning(f"Gemini rate limit or temporary error: {e}")
                raise RuntimeError(f"Rate limit: {e}")
            if "timeout" in error_str or "deadline" in error_str:
                logger.warning(f"Gemini timeout detected: {e}")
                raise RuntimeError(f"Timeout: {e}")
            raise

    # Use asyncio.wait_for with timeout to prevent hanging
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_do_call),
            timeout=120.0  # 120 second overall timeout
        )
    except asyncio.TimeoutError:
        logger.error("Gemini API call timed out after 120 seconds")
        raise RuntimeError("Gemini API timeout - the model is taking too long to respond")


async def _call_ollama(prompt: str, api_key: str, model: str) -> str:
    model = model or "llama3"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "[]")


# ---------------------------------------------------------------------------
# JSON response parser
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_llm_json(raw: str) -> list[dict]:
    fence_match = _FENCE_RE.search(raw)
    if fence_match:
        raw = fence_match.group(1)

    raw = raw.strip()
    if not raw:
        return []

    # Try to extract just the JSON array if there's extra text around it
    # (some LLMs add explanatory text before/after the JSON)
    if not raw.startswith("["):
        bracket_start = raw.find("[")
        if bracket_start != -1:
            raw = raw[bracket_start:]

    if not raw.endswith("]"):
        bracket_end = raw.rfind("]")
        if bracket_end != -1:
            raw = raw[:bracket_end + 1]

    # Fix trailing commas before ] (common LLM mistake)
    raw = re.sub(r",\s*]", "]", raw)
    # Fix trailing commas before } (common LLM mistake)
    raw = re.sub(r",\s*}", "}", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Failed to parse LLM JSON: %.500s", raw)
        return []

    if not isinstance(parsed, list):
        logger.error("LLM returned non-list JSON: %s", type(parsed))
        return []

    required_keys = {"start", "end", "title"}
    valid: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if not required_keys.issubset(item.keys()):
            logger.warning("Skipping invalid suggestion: %s", item)
            continue
        try:
            hashtags = item.get("hashtags", [])
            if isinstance(hashtags, str):
                # LLM returned a single string like "#tag1 #tag2" — split it
                hashtags = [h.strip() for h in hashtags.replace(",", " ").split() if h.strip()]
            elif not isinstance(hashtags, list):
                hashtags = []
            hashtags = [str(h) for h in hashtags if h]

            tags = item.get("tags", [])
            if isinstance(tags, str):
                # LLM returned a single string like "keyword1, keyword2" — split it
                tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
            elif not isinstance(tags, list):
                tags = []
            tags = [str(t) for t in tags if t]

            valid.append({
                "start": float(item["start"]),
                "end": float(item["end"]),
                "title": str(item["title"]),
                "reason": str(item.get("reason", "")),
                "viral_score": int(item.get("viral_score", 5)),
                "hashtags": hashtags,
                "tags": tags,
            })
        except (ValueError, TypeError):
            logger.warning("Skipping suggestion with bad types: %s", item)

    return valid
