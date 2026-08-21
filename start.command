#!/bin/bash
# Double-click to start StudyPlanner (backend + designed frontend, one server).
# First run sets up the virtual environment and installs dependencies.

cd "$(dirname "$0")" || exit 1

# --- find a working Python 3 (Finder launches with a minimal PATH) ---
PY=""
for cand in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3 was not found. Install it from https://www.python.org/downloads/"
  echo "Press Enter to close."; read _; exit 1
fi
echo "Using Python: $($PY --version 2>&1)"

# --- create the virtual environment if missing ---
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  "$PY" -m venv .venv || { echo "Could not create venv."; read _; exit 1; }
fi

# --- make sure the dependencies are actually installed (not just that .venv exists) ---
if ! ./.venv/bin/python -c "import pandas, flask, flask_cors, plotly" 2>/dev/null; then
  echo "Installing dependencies (this can take a minute on the first run)…"
  ./.venv/bin/python -m pip install --upgrade pip >/dev/null
  if ! ./.venv/bin/python -m pip install -r requirements.txt; then
    echo "Dependency installation failed (see messages above)."
    echo "Press Enter to close."; read _; exit 1
  fi
fi

# --- start the server in the background, logging to server.log ---
echo "Starting server…"
./.venv/bin/python frontend.py > server.log 2>&1 &
SERVER_PID=$!

# --- wait until the server actually answers, then open the browser ---
READY=""
for i in $(seq 1 60); do
  if curl -s -o /dev/null "http://127.0.0.1:5050/home"; then READY=1; break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi   # server crashed
  sleep 1
done

if [ "$READY" = "1" ]; then
  open "http://127.0.0.1:5050/home"
  echo ""
  echo "StudyPlanner is running at  http://127.0.0.1:5050/home"
  echo "Keep this window open. Press Ctrl+C to stop."
  wait "$SERVER_PID"
else
  echo ""
  echo "The server did not start. Error log:"
  echo "--------------------------------------------------"
  cat server.log
  echo "--------------------------------------------------"
  echo "Common cause: port 5050 already in use (an old backend still running),"
  echo "or a missing dependency. Send me the lines above if unsure."
fi

echo ""
echo "Press Enter to close."; read _
