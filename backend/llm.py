"""
llm.py — Multi-provider LLM integration for clip suggestion (v4.0 Map-Reduce).
"""

import json
import os
import re
import logging
import asyncio
import random
from typing import Optional, Callable

import httpx  # type: ignore
from tenacity import retry, stop_after_attempt, retry_if_exception

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

    caller = _ModelCaller(provider, api_key, model, progress)

    # Step 1 — Split into chunks of max 8 minutes each (larger chunks = fewer API calls)
    chunks = _chunk_transcript(transcript, chunk_minutes=8)

    logger.info(f"Split transcript into {len(chunks)} chunks for processing")

    # Step 2 — Get candidates from each chunk (MAP).
    # A chunk that still fails after retries is skipped rather than failing
    # the whole project; only if *every* chunk fails do we give up.
    all_candidates = []
    failures: list[Exception] = []
    for i, chunk in enumerate(chunks):
        progress(
            "analyzing",
            55 + (i / len(chunks) * 15),
            f"Analyzing part {i+1} of {len(chunks)}..."
        )
        try:
            candidates = await _analyze_chunk(chunk, i, len(chunks), caller)
            all_candidates.extend(candidates)
        except Exception as exc:
            if not is_retryable(exc):
                # Bad key, unknown model, bad request: every other chunk
                # would fail the same way, so stop now with the real reason.
                raise
            failures.append(exc)
            logger.warning(f"Chunk {i+1}/{len(chunks)} failed after retries, skipping: {exc}")
            progress("analyzing", 55 + ((i + 1) / len(chunks) * 15),
                     f"Warning: part {i+1} of {len(chunks)} could not be analyzed ({friendly_error(exc)}), skipping it")

        # Add delay between chunks to avoid rate limits (skip delay on last chunk)
        if i < len(chunks) - 1:
            await asyncio.sleep(4.0 + random.uniform(0, 2.0))

    if failures and len(failures) == len(chunks):
        raise failures[-1]

    # Step 3 — If only 1 chunk, candidates are already final
    if len(chunks) == 1 or not all_candidates:
        return _validate_suggestions(all_candidates, video_duration)

    # Step 4 — Rank all candidates (REDUCE). If ranking fails or returns
    # nothing usable, rank locally by viral score instead of failing.
    await asyncio.sleep(random.uniform(3.0, 5.0))

    progress("analyzing", 72, "Ranking best moments...")
    final_clips: list[dict] = []
    try:
        final_clips = _validate_suggestions(
            await _rank_candidates(all_candidates, caller),
            video_duration,
        )
    except Exception as exc:
        logger.warning(f"Ranking step failed, ranking locally instead: {exc}")
        progress("analyzing", 73, f"Warning: AI ranking failed ({friendly_error(exc)}), picking the top-scored moments instead")

    if not final_clips:
        final_clips = _validate_suggestions(_rank_locally(all_candidates), video_duration)

    progress("analyzing", 75, f"Found {len(final_clips)} clips")
    return final_clips


def _rank_locally(candidates: list[dict], limit: int = 10) -> list[dict]:
    """Fallback ranking: highest viral score first, no overlaps, at most ``limit``."""
    picked: list[dict] = []
    for c in sorted(candidates, key=lambda c: c.get("viral_score", 0), reverse=True):
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) >= limit:
            break
    return sorted(picked, key=lambda c: c["start"])


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
    caller: "_ModelCaller",
) -> list[dict]:
    """
    Send ONE chunk to LLM. Stay under 1500 tokens.
    """
    prompt = _build_chunk_prompt(chunk, chunk_index, total_chunks)
    raw = await caller.call(prompt)
    logger.info(f"LLM raw response for chunk {chunk_index+1}: {raw[:500]}")
    parsed = _parse_llm_json(raw)
    logger.info(f"Parsed {len(parsed)} clips from chunk {chunk_index+1}")
    return parsed


async def _rank_candidates(
    candidates: list[dict],
    caller: "_ModelCaller",
) -> list[dict]:
    """
    Final reduce step. Send ALL candidates to LLM
    and ask it to pick the best 5-10.
    """
    prompt = _build_reduce_prompt(candidates)
    raw = await caller.call(prompt)
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

    return f"""You are a viral video editor.
This is part {chunk_index+1} of {total_chunks} of a YouTube video transcript.
This section covers timestamps from {chunk_start:.0f}s to {chunk_end:.0f}s.

Find the 3-5 BEST moments in this section suitable for viral short clips.

Rules:
- Each clip MUST be between 60 and 80 seconds long. This is STRICT — no shorter, no longer.
- Clips MUST stay within this section's bounds: {chunk_start:.0f}s to {chunk_end:.0f}s
- Must start and end at natural speech boundaries
- Only pick genuinely strong moments
- You MUST return at least 2-3 clips for this section so we have enough options
- Make sure "start" and "end" are float numbers of seconds
- Generate a catchy, clickbait-style title for each clip (max 8 words)
- Generate 3-5 relevant hashtags for social media (e.g. #motivation #viral)
- Generate 3-5 SEO tags/keywords (single words or short phrases)

TRANSCRIPT SECTION:
{_format_transcript(chunk)}

Return ONLY JSON array:
[
  {{
    "start": <float seconds>,
    "end": <float seconds>,
    "title": "<catchy clickbait title, max 8 words>",
    "reason": "<one sentence>",
    "viral_score": <1-10>,
    "hashtags": ["#tag1", "#tag2", "#tag3"],
    "tags": ["keyword1", "keyword2", "keyword3"]
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
- Return between 5 and 10 clips (each STRICTLY between 60 and 80 seconds long)
- You MUST return AT LEAST 5 clips. This is a strict requirement!
- No overlapping timestamps
- Sort by start time ascending
- "start" and "end" must be float numbers of seconds
- Adjust start/end timestamps if needed to ensure each clip is 60-80 seconds
- Keep the existing title, reason, viral_score, hashtags, and tags from candidates

Return ONLY the selected candidates as JSON array in the exact same format. Do not remove any fields.
[
  {{
    "start": <float seconds>,
    "end": <float seconds>,
    "title": "<catchy clickbait title, max 8 words>",
    "reason": "<one sentence>",
    "viral_score": <1-10>,
    "hashtags": ["#tag1", "#tag2", "#tag3"],
    "tags": ["keyword1", "keyword2", "keyword3"]
  }}
]"""

# ---------------------------------------------------------------------------
# Provider wrappers
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """An LLM provider returned an error. ``status`` is the HTTP status code (0 if unknown)."""
    def __init__(self, message: str, status: int = 0, retry_after: float = 0.0):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


# 408 timeout, 409 conflict, 429 rate limit, 5xx server trouble, 529 Anthropic "overloaded"
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


def is_retryable(exc: BaseException) -> bool:
    """Whether trying again could succeed. A wrong API key, unknown model or bad request never will."""
    if isinstance(exc, ProviderError):
        return exc.status in _RETRYABLE_STATUS
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    # Network trouble: timeouts, dropped connections, DNS hiccups
    return isinstance(exc, (httpx.TransportError, asyncio.TimeoutError, TimeoutError, ConnectionError))


def friendly_error(exc: BaseException) -> str:
    """Short, human explanation for the UI."""
    status = getattr(exc, "status", 0)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    if status in (401, 403):
        return "the API key was rejected - check it in Settings"
    if status == 404:
        return "the model name was not found - check it in Settings"
    if status == 400:
        return f"the provider rejected the request: {exc}"
    if status == 429:
        return "rate limit or quota reached - wait a bit or check your plan"
    if status in (500, 502, 503, 529):
        return "the AI provider is having trouble right now"
    if status in (408, 504) or isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return "the AI provider took too long to answer"
    if isinstance(exc, httpx.TransportError):
        return "could not reach the AI provider - check your internet connection"
    return str(exc)


def _wait_before_retry(retry_state) -> float:
    """Honour the provider's retry-after when it sends one, else back off exponentially (2s..60s) with jitter."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    retry_after = getattr(exc, "retry_after", 0) or 0
    if retry_after > 0:
        return min(retry_after, 90) + random.uniform(0.5, 3)
    backoff = min(60.0, 2.0 * (2 ** (retry_state.attempt_number - 1)))
    return backoff + random.uniform(0, backoff / 2)


def _log_retry(retry_state) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "LLM call failed (attempt %d): %s - retrying in %.1fs",
        retry_state.attempt_number, exc, retry_state.next_action.sleep if retry_state.next_action else 0,
    )


# Model to switch to when the chosen one stays overloaded (503 "high demand",
# 429, timeouts). Only used when it differs from the chosen model.
_FALLBACK_MODELS = {
    "gemini": "gemini-3.5-flash",
}
_ATTEMPTS_BEFORE_FALLBACK = 3


class _ModelCaller:
    """
    Calls the chosen model for one project run. If it keeps failing with an
    error that can pass (overloaded, rate limited, too slow), switches to the
    provider's fallback model and stays on it for the rest of the run, so
    later chunks don't wait through the same failures again.
    """

    def __init__(self, provider: str, api_key: str, model: str, progress: Callable[[str, float, str], None]):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.fallback = _FALLBACK_MODELS.get(provider)
        if not self.fallback or self.fallback == (model or self.fallback):
            self.fallback = None
        self.progress = progress

    async def call(self, prompt: str) -> str:
        if not self.fallback:
            return await _call_provider_with_retry(self.provider, self.api_key, self.model, prompt)
        try:
            return await _call_provider_with_retry.retry_with(
                stop=stop_after_attempt(_ATTEMPTS_BEFORE_FALLBACK)
            )(self.provider, self.api_key, self.model, prompt)
        except Exception as exc:
            if not is_retryable(exc):
                raise
            logger.warning(f"{self.model} keeps failing ({exc}); switching to {self.fallback}")
            self.progress("analyzing", 60, f"Warning: {self.model} is unavailable ({friendly_error(exc)}), switching to {self.fallback}")
            self.model, self.fallback = self.fallback, None
            return await _call_provider_with_retry(self.provider, self.api_key, self.model, prompt)


def _retry_after_header(resp: httpx.Response) -> float:
    try:
        return float(resp.headers.get("retry-after", "") or 0)
    except ValueError:
        return 0.0


@retry(
    stop=stop_after_attempt(5),
    wait=_wait_before_retry,
    retry=retry_if_exception(is_retryable),
    before_sleep=_log_retry,
    reraise=True,
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
        raise ProviderError(f"Unknown LLM provider: {provider}", status=400)

    try:
        return await handler(prompt, api_key, model)
    except httpx.HTTPStatusError as e:
        body = e.response.text[:300]
        raise ProviderError(
            f"{provider} returned HTTP {e.response.status_code}: {body}",
            status=e.response.status_code,
            retry_after=_retry_after_header(e.response),
        ) from e


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
    model = model or "claude-sonnet-5-5"
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


# How long Google may spend on one request. google-genai also sends this to
# Google as the server-side deadline (X-Server-Timeout), so a short value
# makes Google itself abort with 504 DEADLINE_EXCEEDED on long transcripts.
# One 8-minute chunk normally answers in well under a minute with low
# thinking; 2 minutes leaves room without making a stuck request cost 5.
_GEMINI_DEADLINE_S = 120


async def _call_gemini(prompt: str, api_key: str, model: str) -> str:
    try:
        from google import genai
        from google.genai import types, errors as genai_errors
    except ImportError as exc:
        raise RuntimeError("Gemini SDK missing. Install with: pip install google-genai") from exc

    model = model or "gemini-3.5-flash"
    api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ProviderError("Gemini API key missing. Set it in Settings or the GEMINI_API_KEY env var.", status=401)

    client = genai.Client(api_key=api_key, http_options={"timeout": _GEMINI_DEADLINE_S * 1000})

    async def _generate(thinking) -> str:
        config = types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type="application/json",
            thinking_config=thinking,
        )
        response = await asyncio.wait_for(
            client.aio.models.generate_content(model=model, contents=prompt, config=config),
            timeout=_GEMINI_DEADLINE_S + 30,
        )
        return response.text or "[]"

    logger.info(f"Calling Gemini with model: {model} ({len(prompt)} chars)")
    try:
        # Finding clip moments doesn't need deep reasoning, and low thinking
        # keeps responses fast enough to stay well inside the deadline.
        try:
            result = await _generate(types.ThinkingConfig(thinking_level="low"))
        except genai_errors.ClientError as e:
            if e.code == 400 and "think" in str(e).lower():
                # Older models (e.g. 2.x) don't accept thinking_level
                result = await _generate(None)
            else:
                raise
    except genai_errors.APIError as e:
        raise ProviderError(f"Gemini API error: {e}", status=e.code or 0) from e
    except asyncio.TimeoutError as e:
        raise ProviderError(f"Gemini did not answer within {_GEMINI_DEADLINE_S}s", status=504) from e

    logger.info(f"Gemini response received ({len(result)} chars)")
    return result


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
