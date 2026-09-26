"""
Startup Script for NovaPharma Commercial Analytics Assistant.
Launches the FastAPI server and serves the web application locally.
"""

import uvicorn
from backend.db import init_database

def main():
    print("=================================================================")
    print("   NovaPharma Commercial Analytics Assistant (NL-to-SQL)")
    print("=================================================================")
    print("[1/2] Verifying database and schema...")
    init_database()
    print("[2/2] Launching local web server on http://localhost:8000 ...")
    print(">>> Open your browser at: http://localhost:8000")
    print("=================================================================\n")
    
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
