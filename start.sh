#!/bin/bash

# Color definitions for gorgeous terminal output
GREEN='\033[0;32m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}================================================================${NC}"
echo -e "${PURPLE}           STOCKER - AUTOMATED OPTIONS TRADING CORE             ${NC}"
echo -e "${CYAN}================================================================${NC}"
echo ""

# Exit handler to cleanly terminate background jobs
cleanup() {
  echo -e "\n${YELLOW}Stopping Stocker execution engines and servers...${NC}"
  kill "$BACKEND_PID" 2>/dev/null
  kill "$FRONTEND_PID" 2>/dev/null
  echo -e "${GREEN}All servers stopped successfully. Goodbye!${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

# Check Python env
if ! command -v python3 &> /dev/null; then
  echo -e "${RED}Error: Python3 is not installed or not in PATH.${NC}"
  exit 1
fi

# Check Node env
if ! command -v npm &> /dev/null; then
  echo -e "${RED}Error: Node/npm is not installed or not in PATH.${NC}"
  exit 1
fi

# Starting Backend
echo -e "${CYAN}[1/3] Setting up Python Backend Engine...${NC}"
cd backend
if [ ! -d "venv" ]; then
  echo -e "${YELLOW}Creating virtual environment (venv)...${NC}"
  python3 -m venv venv
fi

source venv/bin/activate
echo -e "${YELLOW}Checking/Installing backend dependencies from requirements.txt...${NC}"
pip install --upgrade pip &> /dev/null
pip install -r requirements.txt

echo -e "${GREEN}Starting Uvicorn FastAPI Backend on http://localhost:8000...${NC}"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

cd ..

# Wait for backend to spin up
sleep 3

# Starting Frontend
echo -e "${CYAN}[2/3] Spinning up React Frontend Dashboard...${NC}"
cd frontend

echo -e "${GREEN}Launching Next.js Dev Server on http://localhost:5173...${NC}"
npx next dev -p 5173 -H 127.0.0.1 &
FRONTEND_PID=$!

cd ..

echo ""
echo -e "${GREEN}================================================================${NC}"
echo -e "${PURPLE}🚀 Stocker Application has successfully launched!${NC}"
echo -e "${CYAN}👉 Backend REST & WS: ${NC}http://localhost:8000"
echo -e "${CYAN}👉 Frontend Dashboard: ${NC}http://localhost:5173"
echo -e "${YELLOW}Press [Ctrl+C] at any time to shutdown both servers cleanly.${NC}"
echo -e "${GREEN}================================================================${NC}"
echo ""

# Keep shell open
wait
