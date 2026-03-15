#!/bin/bash
# start.sh — Start both OpenClip servers

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "          Starting OpenClip"
echo "=========================================="
echo ""

# ==========================================
# Check if .env files exist
# ==========================================
SETUP_NEEDED=0

if [ ! -f "backend/.env" ]; then
    echo -e "${RED}Error:${NC} backend/.env not found"
    SETUP_NEEDED=1
fi

if [ ! -f "frontend/.env.local" ]; then
    echo -e "${RED}Error:${NC} frontend/.env.local not found"
    SETUP_NEEDED=1
fi

if [ $SETUP_NEEDED -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}Please run setup first:${NC}"
    echo ""
    echo "  bash setup.sh"
    echo ""
    exit 1
fi

# ==========================================
# Check dependencies
# ==========================================
if ! command -v yt-dlp &> /dev/null; then
    echo -e "${YELLOW}Warning:${NC} yt-dlp not found. Video downloads will fail."
    echo "  Install: pip install yt-dlp"
    echo ""
fi

if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}Warning:${NC} ffmpeg not found. Video processing will fail."
    echo ""
fi

# ==========================================
# Start Backend
# ==========================================
echo "Starting backend server..."
cd backend

# Use virtual environment if present
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python -m uvicorn api:app --reload --port 8000 &
BACKEND_PID=$!

cd ..

# Give backend a moment to start
sleep 2

# ==========================================
# Start Frontend
# ==========================================
echo "Starting frontend server..."
cd frontend
npm run dev &
FRONTEND_PID=$!

cd ..

# ==========================================
# Print status
# ==========================================
echo ""
echo -e "${GREEN}=========================================="
echo "         OpenClip is running!"
echo "==========================================${NC}"
echo ""
echo -e "  ${CYAN}Frontend:${NC}  http://localhost:3000"
echo -e "  ${CYAN}Backend:${NC}   http://localhost:8000"
echo -e "  ${CYAN}API Docs:${NC}  http://localhost:8000/docs"
echo ""
echo "  Backend PID:  $BACKEND_PID"
echo "  Frontend PID: $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop both servers."
echo ""

# ==========================================
# Handle shutdown
# ==========================================
trap "echo ''; echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

wait
