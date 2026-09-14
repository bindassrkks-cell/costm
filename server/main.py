import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Pak Workspace Enterprise API",
    version="2.0.0",
    description="High-performance backend API for mobile apps and web workspace."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE = BASE_DIR / "workspace"

FOLDERS: Dict[str, Path] = {
    "Original": WORKSPACE / "Original",
    "Unpack": WORKSPACE / "Unpack",
    "Editor": WORKSPACE / "Editor",
    "Repack": WORKSPACE / "Repack",
}

MAX_UPLOAD_SIZE = 1024 * 1024 * 1024  # 1 GB

for directory in FOLDERS.values():
    directory.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# UTILITY & SECURITY HELPERS
# --------------------------------------------------

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def resolve_safe_path(folder_name: str, filename: str) -> Path:
    if folder_name not in FOLDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid folder: {folder_name}"
        )

    target_dir = FOLDERS[folder_name].resolve()
    clean_name = Path(filename).name
    file_path = (target_dir / clean_name).resolve()

    # Prevent path traversal
    if not str(file_path).startswith(str(target_dir)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Directory traversal detected."
        )

    return file_path


def scan_folder(directory: Path, folder_key: str) -> List[Dict[str, Any]]:
    if not directory.exists():
        return []

    results = []
    for item in sorted(directory.rglob("*")):
        if item.is_file() and not item.name.startswith("."):
            stat = item.stat()
            rel_path = str(item.relative_to(directory))
            results.append({
                "name": item.name,
                "relative_path": rel_path,
                "folder": folder_key,
                "size_bytes": stat.st_size,
                "size_formatted": format_size(stat.st_size),
                "modified_at": int(stat.st_mtime),
                "download_url": f"/api/download/{folder_key}/{rel_path}"
            })
    return results


# --------------------------------------------------
# MODELS
# --------------------------------------------------

class ProcessRequest(BaseModel):
    filename: str
    clean_destination: bool = False


# --------------------------------------------------
# CORE API ENDPOINTS (MOBILE & SYSTEM)
# --------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "service": "pak-server-core",
        "timestamp": int(time.time()),
        "version": "2.0.0"
    }


@app.get("/api/status")
async def system_status():
    stats = {}
    total_files = 0
    total_bytes = 0

    for name, path in FOLDERS.items():
        files = scan_folder(path, name)
        folder_size = sum(f["size_bytes"] for f in files)
        stats[name] = {
            "count": len(files),
            "size_bytes": folder_size,
            "size_formatted": format_size(folder_size)
        }
        total_files += len(files)
        total_bytes += folder_size

    return {
        "status": "online",
        "totals": {
            "files": total_files,
            "storage_bytes": total_bytes,
            "storage_formatted": format_size(total_bytes)
        },
        "folders": stats
    }


@app.get("/api/workspace")
async def get_workspace():
    return {
        "status": "ok",
        "workspace": {
            name: scan_folder(path, name)
            for name, path in FOLDERS.items()
        }
    }


@app.get("/api/files/{folder}")
async def get_folder_files(folder: str):
    if folder not in FOLDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target folder."
        )
    return {
        "status": "ok",
        "folder": folder,
        "files": scan_folder(FOLDERS[folder], folder)
    }


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    folder: str = Query("Original", description="Destination folder")
):
    if folder not in FOLDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target folder '{folder}' does not exist."
        )

    filename = Path(file.filename or "uploaded_asset.bin").name
    destination = resolve_safe_path(folder, filename)
    total_bytes = 0

    try:
        with destination.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File exceeds maximum allowed limit (1GB)."
                    )
                buffer.write(chunk)
    finally:
        await file.close()

    return {
        "status": "success",
        "filename": filename,
        "folder": folder,
        "size_bytes": total_bytes,
        "size_formatted": format_size(total_bytes),
        "download_url": f"/api/download/{folder}/{filename}"
    }


@app.get("/api/download/{folder}/{filename:path}")
async def download_file(folder: str, filename: str):
    target_file = resolve_safe_path(folder, filename)

    if not target_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested asset not found."
        )

    return FileResponse(
        path=target_file,
        filename=target_file.name,
        media_type="application/octet-stream"
    )


@app.delete("/api/files/{folder}/{filename:path}")
async def delete_file(folder: str, filename: str):
    target_file = resolve_safe_path(folder, filename)

    if not target_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File does not exist."
        )

    target_file.unlink()
    return {
        "status": "success",
        "message": f"Deleted {filename} from {folder}."
    }


@app.post("/api/workspace/clear")
async def clear_workspace(folder: Optional[str] = Query(None)):
    cleared = []
    targets = [folder] if folder and folder in FOLDERS else list(FOLDERS.keys())

    for key in targets:
        folder_path = FOLDERS[key]
        for item in folder_path.iterdir():
            if item.name.startswith("README"):
                continue
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        cleared.append(key)

    return {
        "status": "success",
        "cleared_folders": cleared
    }


# --------------------------------------------------
# PIPELINE ACTIONS (UNPACK & REPACK)
# --------------------------------------------------

@app.post("/api/process/unpack")
async def trigger_unpack(payload: ProcessRequest):
    source_file = resolve_safe_path("Original", payload.filename)

    if not source_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file not found in Original folder."
        )

    unpack_dir = FOLDERS["Unpack"]
    editor_dir = FOLDERS["Editor"]

    if payload.clean_destination:
        for p in [unpack_dir, editor_dir]:
            for item in p.iterdir():
                if not item.name.startswith("README"):
                    if item.is_file(): item.unlink()
                    elif item.is_dir(): shutil.rmtree(item)

    # Extracted asset pipeline demonstration
    output_stub = unpack_dir / f"{source_file.stem}_extracted.dat"
    output_stub.write_bytes(b"EXTRACTED_PAYLOAD_READY_FOR_APP")

    editor_copy = editor_dir / f"{source_file.stem}_editable.json"
    editor_copy.write_text('{"status": "ready_for_customization", "version": 1}')

    return {
        "status": "success",
        "message": "Asset unpacked successfully.",
        "files_generated": [
            f"Unpack/{output_stub.name}",
            f"Editor/{editor_copy.name}"
        ]
    }


@app.post("/api/process/repack")
async def trigger_repack(payload: ProcessRequest):
    editor_files = scan_folder(FOLDERS["Editor"], "Editor")

    if not editor_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Editor directory has no files to repack."
        )

    target_name = payload.filename if payload.filename.endswith(".pak") else f"{payload.filename}.pak"
    output_pak = resolve_safe_path("Repack", target_name)

    output_pak.write_bytes(b"REPACKED_FINAL_BINARY_ARCHIVE")

    return {
        "status": "success",
        "message": "Repack completed successfully.",
        "output_file": target_name,
        "download_url": f"/api/download/Repack/{target_name}"
    }


# --------------------------------------------------
# WEB DASHBOARD (MOBILE-RESPONSIVE)
# --------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Enterprise Pak Server</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f0f6fc; margin: 0; display: flex; align-items: center; justify-content: center; height: 100vh; }
            .card { background: #131b2e; border: 1px solid #243049; border-radius: 16px; padding: 40px; text-align: center; max-width: 480px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            h1 { margin: 0 0 12px; font-size: 26px; color: #58a6ff; }
            p { color: #8b949e; line-height: 1.5; font-size: 15px; margin-bottom: 24px; }
            .btn { display: inline-block; background: #238636; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; transition: 0.2s ease; }
            .btn:hover { background: #2ea043; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>📦 Pak Control Center</h1>
            <p>Backend API and Asset Management Gateway is running with Android/iOS application support.</p>
            <a href="/pak" class="btn">Open Interactive Console</a>
        </div>
    </body>
    </html>
    """


@app.get("/pak", response_class=HTMLResponse)
async def pak_dashboard():
    return """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Pak Workspace Dashboard</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding-bottom: 50px; }
            header { background: #161b22; border-bottom: 1px solid #30363d; padding: 20px 32px; display: flex; justify-content: space-between; align-items: center; }
            .badge { background: #238636; color: #fff; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
            main { max-width: 1200px; margin: 24px auto; padding: 0 16px; }
            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
            .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; }
            .card h3 { font-size: 15px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
            .card .metric { font-size: 28px; font-weight: 700; margin-top: 8px; color: #58a6ff; }
            .toolbar { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 24px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
            input[type=file], select, button { padding: 10px 14px; border-radius: 8px; border: 1px solid #30363d; background: #21262d; color: #fff; font-size: 14px; }
            button { background: #238636; border-color: #2ea043; cursor: pointer; font-weight: 600; }
            button:hover { background: #2ea043; }
            button.danger { background: #da3633; border-color: #f85149; }
            button.danger:hover { background: #b62324; }
            .console-box { background: #010409; border: 1px solid #30363d; border-radius: 12px; padding: 16px; font-family: monospace; font-size: 13px; color: #7ee787; min-height: 200px; max-height: 450px; overflow-y: auto; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <header>
            <h2>⚙️ Pak Workspace Console</h2>
            <span class="badge">● Online 2.0</span>
        </header>
        <main>
            <div class="stats-grid" id="statsGrid"></div>

            <div class="toolbar">
                <input type="file" id="filePicker">
                <select id="targetFolder">
                    <option value="Original">Original</option>
                    <option value="Editor">Editor</option>
                    <option value="Repack">Repack</option>
                </select>
                <button onclick="uploadAsset()">⬆ Upload Asset</button>
                <button onclick="loadWorkspace()">🔄 Refresh State</button>
                <button class="danger" onclick="clearWorkspace()">🗑 Clear Current</button>
            </div>

            <div class="console-box" id="logConsole">Connecting to workspace engine...</div>
        </main>

        <script>
            const logger = document.getElementById("logConsole");
            const statsGrid = document.getElementById("statsGrid");

            function log(data) {
                logger.textContent = typeof data === "object" ? JSON.stringify(data, null, 2) : data;
            }

            async function loadWorkspace() {
                try {
                    const res = await fetch("/api/status");
                    const data = await res.json();
                    renderStats(data.folders);

                    const ws = await fetch("/api/workspace");
                    log(await ws.json());
                } catch (err) {
                    log("Connection error: " + err);
                }
            }

            function renderStats(folders) {
                statsGrid.innerHTML = "";
                for (const [name, info] of Object.entries(folders)) {
                    statsGrid.innerHTML += `
                        <div class="card">
                            <h3>${name}</h3>
                            <div class="metric">${info.count} <span style="font-size:14px;color:#8b949e">files</span></div>
                            <div style="font-size:12px;color:#8b949e;margin-top:4px">${info.size_formatted}</div>
                        </div>
                    `;
                }
            }

            async function uploadAsset() {
                const picker = document.getElementById("filePicker");
                const folder = document.getElementById("targetFolder").value;
                if (!picker.files.length) {
                    alert("Select a file first.");
                    return;
                }
                const form = new FormData();
                form.append("file", picker.files[0]);

                log("Uploading to " + folder + "...");
                try {
                    const res = await fetch(`/api/upload?folder=${folder}`, {
                        method: "POST",
                        body: form
                    });
                    log(await res.json());
                    picker.value = "";
                    loadWorkspace();
                } catch (err) {
                    log("Upload Failed: " + err);
                }
            }

            async function clearWorkspace() {
                const folder = document.getElementById("targetFolder").value;
                if (!confirm(`Are you sure you want to clean ${folder}?`)) return;
                const res = await fetch(`/api/workspace/clear?folder=${folder}`, { method: "POST" });
                log(await res.json());
                loadWorkspace();
            }

            loadWorkspace();
        </script>
    </body>
    </html>
    """
