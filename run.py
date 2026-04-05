#!/usr/bin/env python3
import uvicorn
from app.main import app

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║     Science Distributor - AI-powered Article Distribution   ║
    ║                      Real-time Updates Active                ║
    ╚══════════════════════════════════════════════════════════════╝
    
    🌐 Web interface: http://localhost:8000
    🔌 WebSocket: ws://localhost:8000/ws/{user_id}
    📡 Real-time updates: Active (checking every 30 seconds)
    
    Press Ctrl+C to stop
    """)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )