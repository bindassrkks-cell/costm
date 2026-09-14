from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

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

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE = BASE_DIR / "workspace"

FOLDERS = {
    "Original": WORKSPACE / "Original",
    "Unpack": WORKSPACE / "Unpack",
    "Editor": WORKSPACE / "Editor",
    "Repack": WORKSPACE / "Repack",
}

for folder in FOLDERS.values():
    folder.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Pak Server</title>
    </head>
    <body style="font-family:Arial;padding:30px">
        <h1>Pak Server</h1>
        <p>Server is online.</p>
        <a href="/pak">Open Pak Dashboard</a>
    </body>
    </html>
    """


@app.get("/pak", response_class=HTMLResponse)
async def pak_dashboard():
    return """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">

        <title>Pak Workspace Dashboard</title>

        <style>
            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                background: #0d1117;
                color: #f0f6fc;
                font-family: Arial, sans-serif;
            }

            header {
                padding: 20px;
                background: #161b22;
                border-bottom: 1px solid #30363d;
            }

            h1 {
                margin: 0 0 6px;
            }

            .status {
                color: #3fb950;
                font-size: 14px;
            }

            main {
                padding: 20px;
                max-width: 1100px;
                margin: auto;
            }

            .grid {
                display: grid;
                grid-template-columns:
                    repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
            }

            .card {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 14px;
                padding: 20px;
            }

            .folder {
                font-size: 42px;
                margin-bottom: 10px;
            }

            .name {
                font-size: 20px;
                font-weight: bold;
            }

            .path {
                color: #8b949e;
                margin-top: 7px;
                font-size: 13px;
            }

            .actions {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 25px;
            }

            button {
                border: 0;
                border-radius: 9px;
                padding: 12px 18px;
                font-size: 15px;
                cursor: pointer;
                background: #238636;
                color: white;
            }

            button.secondary {
                background: #21262d;
                border: 1px solid #30363d;
            }

            #result {
                margin-top: 20px;
                padding: 15px;
                background: #010409;
                border: 1px solid #30363d;
                border-radius: 10px;
                white-space: pre-wrap;
                color: #8b949e;
            }
        </style>
    </head>

    <body>

        <header>
            <h1>📦 Pak Workspace</h1>
            <div class="status">● Server Online</div>
        </header>

        <main>

            <div class="grid">

                <div class="card">
                    <div class="folder">📁</div>
                    <div class="name">Original</div>
                    <div class="path">workspace/Original</div>
                </div>

                <div class="card">
                    <div class="folder">📁</div>
                    <div class="name">Unpack</div>
                    <div class="path">workspace/Unpack</div>
                </div>

                <div class="card">
                    <div class="folder">📁</div>
                    <div class="name">Editor</div>
                    <div class="path">workspace/Editor</div>
                </div>

                <div class="card">
                    <div class="folder">📁</div>
                    <div class="name">Repack</div>
                    <div class="path">workspace/Repack</div>
                </div>

            </div>

            <div class="actions">

                <button onclick="checkWorkspace()">
                    🔄 Refresh Workspace
                </button>

                <button class="secondary"
                        onclick="location.href='/api/health'">
                    ❤️ API Health
                </button>

            </div>

            <div id="result">
                Ready.
            </div>

        </main>

        <script>
            async function checkWorkspace() {
                const result = document.getElementById("result");

                result.textContent = "Loading...";

                try {
                    const response =
                        await fetch("/api/workspace");

                    const data =
                        await response.json();

                    result.textContent =
                        JSON.stringify(data, null, 2);

                } catch (error) {
                    result.textContent =
                        "ERROR: " + error;
                }
            }
        </script>

    </body>
    </html>
    """


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "pak-server",
        "api": "online"
    }


@app.get("/api/workspace")
async def workspace():
    result = {}

    for name, folder in FOLDERS.items():
        files = []

        if folder.exists():
            for item in folder.rglob("*"):
                if item.is_file():
                    files.append(
                        str(item.relative_to(folder))
                    )

        result[name] = files

    return {
        "status": "ok",
        "workspace": result
    }