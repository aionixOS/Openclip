"""
gemini_transcriber.py — Speech-to-text with Gemini Transcribe Live.

``gemini-3.5-transcribe-live`` is a Live API (bidirectional WebSocket) model
made for transcribing a microphone in real time. A downloaded video can be
transcribed by streaming its audio track instead of a microphone:

    1. FFmpeg decodes the audio to 16 kHz mono 16-bit PCM, the Live API's
       input format.
    2. The audio is cut into short pieces (about 4-12 s) at the quietest
       moment in each stretch, so cuts land in pauses between words.
       Pieces that are only silence are skipped.
    3. Each piece is streamed in its own Live session (a few at a time) and
       the session's transcription of that piece is collected.
    4. The model returns text only, without timestamps. Each piece's start
       and end are known, so words are spread across the part of the piece
       where there is sound, weighted by word length. That gives the
       per-word timings the captioner needs, accurate to a fraction of a
       second because the pieces are short.

The result has the same shape as the YouTube caption parser's output:
``[{"start", "end", "text", "words": [{"word", "start", "end"}]}]``.
"""

import asyncio
import logging
import re
import subprocess
from typing import Callable, Optional

import numpy as np  # type: ignore

import ffbin  # type: ignore

logger = logging.getLogger(__name__)

MODEL = "models/gemini-3.5-transcribe-live"

SAMPLE_RATE = 16000          # Live API input format: 16 kHz, mono, 16-bit PCM
FRAME_S = 0.02               # loudness is measured in 20 ms frames
MIN_PIECE_S = 4.0            # pieces are cut between 4 and 12 seconds long,
MAX_PIECE_S = 12.0           # at the quietest point in that range
SEND_CHUNK_S = 0.1           # audio is sent in 100 ms messages, as a mic would,
SEND_SPEEDUP = 8             # but 8x faster than real time
QUIET_AFTER_END_S = 3.0      # after the last audio, stop once the model is quiet this long
CONCURRENCY = 4              # Live sessions open at once
PIECE_TIMEOUT_S = 60         # one piece must be transcribed within this
PIECE_ATTEMPTS = 3

# Missing spaces the model sometimes leaves when it joins partial results,
# e.g. "straightPut", "it.Now" or "IHave" -> split before the capital letter.
# Needs 3+ lowercase letters before it so names like "McDonald" or
# "iPhone" stay whole.
_GLUED_CAPITAL = re.compile(r"(?:(?<=[a-z]{3})|(?<=[,.!?])|(?<=\bI))(?=[A-Z][a-z])")


class TranscriptionError(Exception):
    """Gemini Live could not transcribe the audio."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def transcribe(
    video_path: str,
    api_key: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> list[dict]:
    """
    Transcribe a video's audio with Gemini Transcribe Live.

    Args:
        video_path:        Path to the downloaded video (any format FFmpeg reads).
        api_key:           Gemini API key.
        progress_callback: Called with (percent 0-100, message).

    Returns:
        Transcript segments with word timings (see module docstring).

    Raises:
        TranscriptionError: If the audio can't be read or too many pieces fail.
    """
    from google import genai

    def notify(pct: float, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)

    notify(0, "Gemini Live: reading the audio track...")
    pcm = await asyncio.to_thread(_decode_audio, video_path)
    if pcm.size == 0:
        raise TranscriptionError("The video has no audio track")

    rms = _frame_loudness(pcm)
    threshold = _speech_threshold(rms)
    pieces = [p for p in _split_at_pauses(rms) if rms[p[0]:p[1]].max() > threshold]
    total_s = pcm.size / SAMPLE_RATE
    logger.info("Gemini Live: %.0fs of audio in %d pieces", total_s, len(pieces))
    if not pieces:
        return []

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    semaphore = asyncio.Semaphore(CONCURRENCY)
    results: list[Optional[str]] = [None] * len(pieces)
    done = 0
    failed = 0

    async def work(i: int, start_f: int, end_f: int) -> None:
        nonlocal done, failed
        audio = pcm[_f2s(start_f):_f2s(end_f)].tobytes()
        async with semaphore:
            for attempt in range(1, PIECE_ATTEMPTS + 1):
                try:
                    results[i] = await asyncio.wait_for(
                        _transcribe_piece(client, audio), timeout=PIECE_TIMEOUT_S
                    )
                    break
                except Exception as exc:  # network drop, rate limit, timeout...
                    if _is_auth_error(exc):
                        raise TranscriptionError(f"Gemini rejected the API key: {exc}") from exc
                    logger.warning("Gemini Live piece %d attempt %d failed: %s: %s", i + 1, attempt, type(exc).__name__, exc)
                    if attempt < PIECE_ATTEMPTS:
                        await asyncio.sleep(2 * attempt)
            else:
                failed += 1
        done += 1
        notify(5 + 95 * done / len(pieces), f"Gemini Live: transcribed {done} of {len(pieces)} parts")

    await asyncio.gather(*(work(i, s, e) for i, (s, e) in enumerate(pieces)))

    if failed > max(1, len(pieces) // 10):
        raise TranscriptionError(f"{failed} of {len(pieces)} audio parts could not be transcribed")

    segments = []
    for (start_f, end_f), text in zip(pieces, results):
        if text:
            seg = _timed_segment(text, rms, start_f, end_f, threshold)
            if seg:
                segments.append(seg)
    logger.info("Gemini Live: %d segments, %d parts failed", len(segments), failed)
    return segments


# ---------------------------------------------------------------------------
# Audio preparation
# ---------------------------------------------------------------------------

def _decode_audio(video_path: str) -> np.ndarray:
    cmd = [
        ffbin.ffmpeg(), "-v", "error", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError("Reading the audio took longer than 10 minutes") from exc
    if result.returncode != 0:
        raise TranscriptionError(f"FFmpeg could not read the audio: {result.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(result.stdout, dtype=np.int16)


def _f2s(frame: int) -> int:
    """Frame index -> sample index."""
    return int(frame * FRAME_S * SAMPLE_RATE)


def _frame_loudness(pcm: np.ndarray) -> np.ndarray:
    """RMS loudness of each 20 ms frame."""
    n = int(FRAME_S * SAMPLE_RATE)
    frames = len(pcm) // n
    if frames == 0:
        return np.zeros(1)
    x = pcm[: frames * n].astype(np.float32).reshape(frames, n)
    return np.sqrt((x * x).mean(axis=1))


def _speech_threshold(rms: np.ndarray) -> float:
    """Loudness above which a frame counts as sound: well above the quiet floor."""
    floor = float(np.percentile(rms, 10))
    loud = float(np.percentile(rms, 90))
    return max(floor + 0.15 * (loud - floor), 50.0)


def _split_at_pauses(rms: np.ndarray) -> list[tuple[int, int]]:
    """Cut the audio into MIN..MAX second pieces at the quietest 200 ms in each window."""
    per_s = 1 / FRAME_S
    smooth = np.convolve(rms, np.ones(10) / 10, mode="same")  # 200 ms average
    lo, hi = int(MIN_PIECE_S * per_s), int(MAX_PIECE_S * per_s)
    pieces, start, n = [], 0, len(rms)
    while start < n:
        if n - start <= hi:
            pieces.append((start, n))
            break
        window = smooth[start + lo: start + hi]
        cut = start + lo + int(np.argmin(window))
        pieces.append((start, cut))
        start = cut
    return pieces


# ---------------------------------------------------------------------------
# Live API
# ---------------------------------------------------------------------------

async def _transcribe_piece(client, audio: bytes) -> str:
    """Stream one piece of audio through a Live session; return its transcription."""
    from google.genai import types

    config = types.LiveConnectConfig(response_modalities=["TEXT"])
    final_parts: list[str] = []
    pending_interim = ""          # text of an utterance that has no final yet
    step = int(SEND_CHUNK_S * SAMPLE_RATE) * 2  # bytes
    # Half a second of silence at the end tells the model the speech is over.
    audio = audio + b"\x00\x00" * int(0.5 * SAMPLE_RATE)
    loop = asyncio.get_running_loop()
    last_msg = loop.time()
    sent_all = asyncio.Event()
    receive_error: list[BaseException] = []

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        async def send() -> None:
            for i in range(0, len(audio), step):
                await session.send_realtime_input(
                    audio=types.Blob(data=audio[i:i + step], mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
                )
                await asyncio.sleep(SEND_CHUNK_S / SEND_SPEEDUP)
            await session.send_realtime_input(audio_stream_end=True)
            sent_all.set()

        async def receive() -> None:
            nonlocal pending_interim, last_msg
            try:
                # receive() yields one turn at a time; a pause inside the
                # piece ends a turn, so keep reading turns until the server
                # closes the session.
                while True:
                    async for msg in session.receive():
                        last_msg = loop.time()
                        sc = msg.server_content
                        if sc is None:
                            continue
                        if sc.input_transcription and sc.input_transcription.text:
                            final_parts.append(sc.input_transcription.text)
                            pending_interim = ""
                        elif sc.interim_input_transcription and sc.interim_input_transcription.text:
                            pending_interim = sc.interim_input_transcription.text
            except Exception as exc:  # the server closes the socket when it's done
                receive_error.append(exc)

        sender = asyncio.create_task(send())
        receiver = asyncio.create_task(receive())
        try:
            await sent_all.wait()
            sent_at = loop.time()
            # Done once the server closes, or once it's been quiet for a
            # moment after all the audio went in.
            while not receiver.done():
                now = loop.time()
                if now - sent_at > 1.5 and now - last_msg > QUIET_AFTER_END_S:
                    break
                await asyncio.sleep(0.1)
        finally:
            sender.cancel()
            receiver.cancel()

    text = " ".join(p.strip() for p in final_parts + [pending_interim] if p.strip())
    if not text and receive_error:
        raise receive_error[0]
    return text


def _is_auth_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code in (401, 403) or "API key not valid" in str(exc)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def _timed_segment(text: str, rms: np.ndarray, start_f: int, end_f: int, threshold: float) -> Optional[dict]:
    """Spread a piece's words across the span of it that has sound."""
    text = _GLUED_CAPITAL.sub(" ", text).strip()
    words = text.split()
    if not words:
        return None

    loud = np.nonzero(rms[start_f:end_f] > threshold)[0]
    if loud.size:
        s_f, e_f = start_f + int(loud[0]), start_f + int(loud[-1]) + 1
    else:
        s_f, e_f = start_f, end_f
    t0, t1 = s_f * FRAME_S, e_f * FRAME_S

    # Longer words take longer to say; +2 gives short words a fair share.
    weights = np.array([len(w.strip(".,!?;:\"'")) + 2 for w in words], dtype=np.float64)
    edges = t0 + (t1 - t0) * np.concatenate([[0.0], np.cumsum(weights) / weights.sum()])
    timed = [
        {"word": w, "start": round(float(edges[i]), 3), "end": round(float(edges[i + 1]), 3)}
        for i, w in enumerate(words)
    ]
    return {"start": timed[0]["start"], "end": timed[-1]["end"], "text": " ".join(words), "words": timed}
