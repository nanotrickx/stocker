#!/bin/bash

# ── Stocker ngrok Tunnel Launcher ──────────────────────────
# Exposes both backend (API) and frontend (Dashboard) via ngrok

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}   STOCKER — ngrok Tunnel Setup                                 ${NC}"
echo -e "${CYAN}================================================================${NC}"
echo ""

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
  echo -e "${RED}Error: ngrok is not installed.${NC}"
  echo -e "${YELLOW}Install it:  brew install ngrok${NC}"
  echo -e "${YELLOW}Then run:    ngrok config add-authtoken YOUR_TOKEN${NC}"
  exit 1
fi

# Check if backend is running
if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
  echo -e "${RED}Error: Backend not running on port 8000.${NC}"
  echo -e "${YELLOW}Start Stocker first:  bash start.sh${NC}"
  exit 1
fi

echo -e "${GREEN}[1/2] Starting ngrok tunnel for Backend (port 8000)...${NC}"
echo ""

# Start ngrok for backend
ngrok http 8000 --log=stdout > /tmp/ngrok_stocker.log 2>&1 &
NGROK_PID=$!
sleep 3

# Extract the public URL from ngrok API
BACKEND_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)

if [ -z "$BACKEND_URL" ]; then
  echo -e "${RED}Failed to get ngrok URL. Check if ngrok is authenticated.${NC}"
  echo -e "${YELLOW}Run:  ngrok config add-authtoken YOUR_TOKEN${NC}"
  kill $NGROK_PID 2>/dev/null
  exit 1
fi

echo -e "${GREEN}✅ Backend tunnel active: ${CYAN}${BACKEND_URL}${NC}"

# Update frontend .env.local
echo -e "${GREEN}[2/2] Configuring frontend to use ngrok backend...${NC}"
echo "NEXT_PUBLIC_API_URL=${BACKEND_URL}" > frontend/.env.local
echo -e "${GREEN}✅ Updated frontend/.env.local${NC}"

echo ""
echo -e "${CYAN}================================================================${NC}"
echo -e "${GREEN}🚀 ngrok Tunnel is LIVE!${NC}"
echo ""
echo -e "  ${CYAN}Backend API:${NC}  ${BACKEND_URL}"
echo -e "  ${CYAN}Frontend:${NC}     http://localhost:5173 (connect locally)"
echo -e "  ${CYAN}ngrok Admin:${NC}  http://localhost:4040"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT:${NC}"
echo -e "  1. Restart the frontend (${YELLOW}npm run dev${NC}) after this script"
echo -e "     so it picks up the new NEXT_PUBLIC_API_URL"
echo -e "  2. Access the frontend at ${CYAN}http://localhost:5173${NC}"
echo -e "     The frontend will call the backend through ngrok"
echo -e "  3. For Zerodha login redirect, use ${CYAN}http://localhost:5173${NC}"
echo -e "     as the redirect URL in your Kite app settings"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the tunnel.${NC}"
echo -e "${CYAN}================================================================${NC}"

# Cleanup on exit
cleanup() {
  echo -e "\n${YELLOW}Stopping ngrok tunnel...${NC}"
  kill $NGROK_PID 2>/dev/null
  # Reset .env.local to local mode
  echo "# NEXT_PUBLIC_API_URL=" > frontend/.env.local
  echo -e "${GREEN}Tunnel stopped. Frontend reset to localhost mode.${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

wait $NGROK_PID
