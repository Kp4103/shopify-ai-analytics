@echo off
echo ========================================
echo   Shopify AI Analytics - Starting...
echo ========================================
echo.

REM Start Python AI Service in new window
echo Starting Python AI Service on port 8000...
start "Python AI Service (port 8000)" cmd /k "cd /d C:\Users\kunal\Desktop\shopify-ai-analytics\python-ai-service && venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

REM Wait for Python service to initialize
timeout /t 3 /nobreak > nul

REM Start Rails API in new window
echo Starting Rails API on port 3000...
start "Rails API (port 3000)" cmd /k "cd /d C:\Users\kunal\Desktop\shopify-ai-analytics\rails-api && bundle exec rails server -p 3000"

echo.
echo ========================================
echo   Services are starting in new windows
echo ========================================
echo.
echo   Python AI Service: http://localhost:8000
echo   Rails API:         http://localhost:3000
echo.
echo   Test with:
echo   curl -X POST http://localhost:3000/api/v1/questions -H "Content-Type: application/json" -d "{\"question\":\"List all my products\", \"store_id\":\"internshala-test.myshopify.com\"}"
echo.
echo ========================================
pause
