from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Pak Workspace Server",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "pak-server"
    }

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "api": "online"
    }

@app.get("/api/workspace")
async def workspace():
    return {
        "folders": [
            "Original",
            "Unpack",
            "Editor",
            "Repack"
        ]
    }
