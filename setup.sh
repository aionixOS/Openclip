#!/bin/bash
# setup.sh — OpenClip Setup Script
# Checks dependencies and installs requirements

set -e

echo "=========================================="
echo "       OpenClip Setup Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0

# ==========================================
# Check Python version (>= 3.11)
# ==========================================
echo -n "Checking Python version... "
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}NOT FOUND${NC}"
    echo "  Please install Python 3.11 or higher"
    echo "  https://www.python.org/downloads/"
    ERRORS=$((ERRORS + 1))
    PYTHON_CMD=""
fi

if [ -n "$PYTHON_CMD" ]; then
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
        echo -e "${GREEN}OK${NC} (Python $PYTHON_VERSION)"
    else
        echo -e "${RED}FAILED${NC} (Python $PYTHON_VERSION)"
        echo "  Python 3.11+ required, found $PYTHON_VERSION"
        echo "  https://www.python.org/downloads/"
        ERRORS=$((ERRORS + 1))
    fi
fi

# ==========================================
# Check Node.js version (>= 18)
# ==========================================
echo -n "Checking Node.js version... "
if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
    FULL_VERSION=$(node -v)

    if [ "$NODE_VERSION" -ge 18 ]; then
        echo -e "${GREEN}OK${NC} ($FULL_VERSION)"
    else
        echo -e "${RED}FAILED${NC} ($FULL_VERSION)"
        echo "  Node.js 18+ required, found $FULL_VERSION"
        echo "  https://nodejs.org/"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}NOT FOUND${NC}"
    echo "  Please install Node.js 18 or higher"
    echo "  https://nodejs.org/"
    ERRORS=$((ERRORS + 1))
fi

# ==========================================
# Check FFmpeg
# ==========================================
echo -n "Checking FFmpeg... "
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')
    echo -e "${GREEN}OK${NC} ($FFMPEG_VERSION)"
else
    echo -e "${RED}NOT FOUND${NC}"
    echo ""
    echo "  FFmpeg is required. Install it:"
    echo ""
    echo "  macOS:    brew install ffmpeg"
    echo "  Ubuntu:   sudo apt install ffmpeg"
    echo "  Windows:  choco install ffmpeg"
    echo "            or download from https://ffmpeg.org/download.html"
    echo ""
    ERRORS=$((ERRORS + 1))
fi

# ==========================================
# Check/Install yt-dlp
# ==========================================
echo -n "Checking yt-dlp... "
if command -v yt-dlp &> /dev/null; then
    YTDLP_VERSION=$(yt-dlp --version 2>&1)
    echo -e "${GREEN}OK${NC} ($YTDLP_VERSION)"
else
    echo -e "${YELLOW}NOT FOUND${NC} - Installing..."
    if [ -n "$PYTHON_CMD" ]; then
        $PYTHON_CMD -m pip install yt-dlp --quiet
        if command -v yt-dlp &> /dev/null; then
            echo -e "  ${GREEN}Installed successfully${NC}"
        else
            echo -e "  ${RED}Installation failed${NC}"
            echo "  Try: pip install yt-dlp"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo "  Cannot install without Python"
        ERRORS=$((ERRORS + 1))
    fi
fi

echo ""

# ==========================================
# Stop if critical errors
# ==========================================
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}=========================================="
    echo "  Setup cannot continue: $ERRORS error(s)"
    echo "==========================================${NC}"
    echo "Please fix the issues above and run setup.sh again."
    exit 1
fi

echo -e "${GREEN}All dependencies found!${NC}"
echo ""

# ==========================================
# Copy .env files if not exist
# ==========================================
echo "Setting up environment files..."

if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        echo -e "  ${GREEN}Created${NC} backend/.env from .env.example"
    fi
else
    echo "  backend/.env already exists"
fi

if [ ! -f "frontend/.env.local" ]; then
    if [ -f "frontend/.env.example" ]; then
        cp frontend/.env.example frontend/.env.local
        echo -e "  ${GREEN}Created${NC} frontend/.env.local from .env.example"
    fi
else
    echo "  frontend/.env.local already exists"
fi

echo ""

# ==========================================
# Install Python dependencies
# ==========================================
echo "Installing Python dependencies..."
cd backend

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
fi

# Activate virtual environment
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

pip install -r requirements.txt --quiet
echo -e "  ${GREEN}Python dependencies installed${NC}"

cd ..

# ==========================================
# Install Node.js dependencies
# ==========================================
echo "Installing Node.js dependencies..."
cd frontend
npm install --silent
echo -e "  ${GREEN}Node.js dependencies installed${NC}"
cd ..

echo ""

# ==========================================
# Create necessary directories
# ==========================================
echo "Creating directories..."
mkdir -p tmp data
echo -e "  ${GREEN}Created${NC} tmp/ and data/ directories"

echo ""
echo -e "${GREEN}=========================================="
echo "         Setup Complete!"
echo "==========================================${NC}"
echo ""
echo "To start OpenClip, run:"
echo ""
echo "  bash start.sh"
echo ""
