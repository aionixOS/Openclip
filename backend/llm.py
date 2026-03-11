"""
llm.py — Multi-provider LLM integration for clip suggestion (v4.0 Map-Reduce).
"""

import json
import re
import logging
import asyncio
from typing import Optional, Callable

import httpx  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_TIMEOUT = 120.0

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

    # Step 1 — Split into chunks of max 3 minutes each
    chunks = _chunk_transcript(transcript, chunk_minutes=3)

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

    # Step 3 — If only 1 chunk, candidates are already final
    if len(chunks) == 1:
        return _validate_suggestions(all_candidates, video_duration)

    # Step 4 — Rank all candidates (REDUCE)
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
    return _parse_llm_json(raw)


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
    """
    logger.info(f"RAW LLM SUGGESTIONS RECEIVED FOR VALIDATION: {suggestions}")
    
    valid = []
    for s in suggestions:
        if s["start"] > s["end"]:
            s["start"], s["end"] = s["end"], s["start"]
            
        if s["start"] < 0 or s["end"] > video_duration:
            logger.warning(f"Dropping clip because it exceeds video bounds (start: {s.get('start')}, end: {s.get('end')}, video_duration: {video_duration})")
            continue
            
        dur = s["end"] - s["start"]
        if dur < 10 or dur > 180:
            logger.warning(f"Dropping clip due to length ({dur}s): {s.get('title')}")
            continue
            
        valid.append(s)
    
    valid.sort(key=lambda x: x["start"])
    
    # Remove overlaps
    non_overlapping = []
    last_end = -1.0
    for s in valid:
        if s["start"] >= last_end:
            non_overlapping.append(s)
            last_end = s["end"]
            
    if not non_overlapping:
        logger.warning("No valid clips survived the validation stage.")
        
    return non_overlapping


def _build_chunk_prompt(chunk: list[dict], chunk_index: int, total_chunks: int) -> str:
    return f"""You are a viral video editor.
This is part {chunk_index+1} of {total_chunks} of a YouTube video transcript.

Find the 3-5 BEST moments in this section suitable for viral short clips.

Rules:
- Each clip: STRICTLY 60 seconds (must be between 50 and 70 seconds)
- Must start and end at natural speech boundaries
- Only pick genuinely strong moments
- You MUST return at least 2-3 clips for this section so we have enough options.
- Make sure "start" and "end" are float numbers of seconds

TRANSCRIPT SECTION:
{_format_transcript(chunk)}

Return ONLY JSON array:
[
  {{
    "start": <float seconds>,
    "end": <float seconds>,
    "title": "<max 8 words>",
    "reason": "<one sentence>",
    "viral_score": <1-10>
  }}
]
If no strong moments found return: []"""


def _build_reduce_prompt(candidates: list[dict]) -> str:
    return f"""You are a viral video editor.
Below are candidate clip moments found across a YouTube video. 
Select the best clips for maximum viral potential.

CANDIDATES:
{_format_candidates(candidates)}

Rules:
- Return between 5 and 10 clips (each STRICTLY 60 seconds long)
- You MUST return AT LEAST 5 clips. This is a strict requirement!
- No overlapping timestamps
- Sort by start time ascending
- "start" and "end" must be float numbers of seconds

Return ONLY the selected candidates as JSON array in the exact same format. Do not change any fields.
[
  {{
    "start": <float seconds>,
    "end": <float seconds>,
    "title": "<max 8 words>",
    "reason": "<one sentence>",
    "viral_score": <1-10>
  }}
]"""

# ---------------------------------------------------------------------------
# Provider wrappers
# ---------------------------------------------------------------------------

@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=10),
  reraise=True
)
async def _call_provider_with_retry(provider: str, api_key: str, model: str, prompt: str) -> str:
    dispatch = {
        "openai": _call_openai,
        "anthropic": _call_anthropic,
        "gemini": _call_gemini,
        "ollama": _call_ollama,
    }
    handler = dispatch.get(provider)
    if handler is None:
        raise ValueError(f"Unknown LLM provider: {provider}")
    return await handler(prompt, api_key, model)


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
    model = model or "gemini-1.5-pro"
    def _do_call() -> str:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type="application/json",
            response_schema={"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "start": {"type": "NUMBER"},
                "end": {"type": "NUMBER"},
                "title": {"type": "STRING"},
                "reason": {"type": "STRING"},
                "viral_score": {"type": "INTEGER"}
            }, "required": ["start", "end", "title", "reason", "viral_score"]}}
        )
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        return response.text
    return await asyncio.to_thread(_do_call)


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

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Failed to parse LLM JSON: %.200s", raw)
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
            valid.append({
                "start": float(item["start"]),
                "end": float(item["end"]),
                "title": str(item["title"]),
                "reason": str(item.get("reason", "")),
                "viral_score": int(item.get("viral_score", 5)),
            })
        except (ValueError, TypeError):
            logger.warning("Skipping suggestion with bad types: %s", item)

    return valid
