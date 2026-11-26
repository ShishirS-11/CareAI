from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
API_HOST = os.getenv("CAREAI_API_HOST", "127.0.0.1")
API_PORT = os.getenv("CAREAI_API_PORT", "8000")
STREAMLIT_HOST = os.getenv("CAREAI_STREAMLIT_HOST", "127.0.0.1")
STREAMLIT_PORT = os.getenv("CAREAI_STREAMLIT_PORT", "8501")


def main() -> int:
    api_command = [
        sys.executable, "-m", "uvicorn", "api.main:app",
        "--host", API_HOST, "--port", API_PORT,
    ]
    streamlit_command = [
        sys.executable, "-m", "streamlit", "run", "main.py",
        "--server.address", STREAMLIT_HOST,
        "--server.port", STREAMLIT_PORT,
    ]

    print("Starting CareAI API...", flush=True)
    api_process = subprocess.Popen(api_command, cwd=ROOT)
    time.sleep(2)
    if api_process.poll() is not None:
        print("CareAI API failed to start. Check the API output above.", flush=True)
        return int(api_process.returncode or 1)

    print(f"CareAI API: http://{API_HOST}:{API_PORT}", flush=True)
    print(f"API documentation: http://{API_HOST}:{API_PORT}/docs", flush=True)
    print("Starting CareAI Streamlit...", flush=True)
    streamlit_process = subprocess.Popen(streamlit_command, cwd=ROOT)
    print(f"CareAI app: http://{STREAMLIT_HOST}:{STREAMLIT_PORT}", flush=True)
    print("Press Ctrl+C to stop both services.", flush=True)

    try:
        while True:
            api_code = api_process.poll()
            streamlit_code = streamlit_process.poll()
            if api_code is not None:
                print(f"CareAI API stopped with exit code {api_code}.", flush=True)
                return int(api_code)
            if streamlit_code is not None:
                print(f"Streamlit stopped with exit code {streamlit_code}.", flush=True)
                return int(streamlit_code)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping CareAI...", flush=True)
        return 0
    finally:
        for process in (streamlit_process, api_process):
            if process.poll() is None:
                process.terminate()
        for process in (streamlit_process, api_process):
            if process.poll() is None:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
