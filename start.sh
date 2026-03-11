#!/bin/bash
# start.sh — Start both OpenClip servers

# Ensure yt-dlp and ffmpeg exist as a quick check
if ! command -v yt-dlp &> /dev/null
then
    echo "yt-dlp could not be found. Please install it."
fi

if ! command -v ffmpeg &> /dev/null
then
    echo "ffmpeg could not be found. Please install it."
fi

# Start Backend
cd backend
# Use virtual environment if present
if [ -d ".venv" ]; then
    source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null
fi
python -m uvicorn api:app --reload --port 8000 &
BACKEND_PID=$!

# Start Frontend
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo "Servers running. Press Ctrl+C to stop."
wait
