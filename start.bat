@echo off
echo ==========================================
echo           Starting OpenClip
echo ==========================================
echo.

start "OpenClip Backend" cmd /k "cd /d ""%~dp0backend"" && .venv\Scripts\python -m uvicorn api:app --host 0.0.0.0 --port 8000"
start "OpenClip Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

echo OpenClip is running:
echo   Frontend: http://localhost:5000
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
