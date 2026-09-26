"""
Startup Script for Pharma Analytics Bot (Commercial Intelligence AI).
Launches the FastAPI server and serves the web application locally.
"""

import uvicorn
from backend.db import init_database

def main():
    print("=================================================================")
    print("   Pharma Analytics Bot (Commercial Intelligence NL-to-SQL)")
    print("=================================================================")
    print("[1/2] Verifying database and schema...")
    init_database()
    import os
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    
    print(f"[2/2] Launching web server on http://{host}:{port} ...")
    print(f">>> Access the web interface at: http://localhost:{port}")
    print("=================================================================\n")
    
    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
