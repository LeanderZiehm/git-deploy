from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import subprocess
from threading import Thread
from typing import Optional

app = FastAPI(title="Git Dashboard")

# --- Global cache to store repo info ---
git_cache = {}

# --- Utility functions ---
def run_git(cmd, repo_path: Path):
    try:
        return subprocess.check_output(
            ["git"] + cmd,
            cwd=repo_path,
            stderr=subprocess.DEVNULL,
            env={"GIT_TERMINAL_PROMPT": "0"}  # don't prompt
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None

def get_git_info(repo_path: Path):
    if not (repo_path / ".git").exists():
        return None

    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    local_commit = run_git(["rev-parse", "HEAD"], repo_path)
    remote_commit = run_git(["rev-parse", f"origin/{branch}"], repo_path) if branch else None

    if not branch or not local_commit:
        return None

    ahead, behind = 0, 0
    ahead_behind = run_git(["rev-list", "--left-right", "--count", f"{branch}...origin/{branch}"], repo_path)
    if ahead_behind:
        ahead, behind = map(int, ahead_behind.split())

    last_local_commit_date = run_git(["log", "-1", "--format=%ci", branch], repo_path)
    last_remote_commit_date = run_git(["log", "-1", "--format=%ci", f"origin/{branch}"], repo_path) if remote_commit else None

    return {
        "name": repo_path.name,
        "path": str(repo_path.resolve()),
        "branch": branch,
        "local_commit": local_commit,
        "remote_commit": remote_commit,
        "ahead": ahead,
        "behind": behind,
        "last_local_commit_date": last_local_commit_date,
        "last_remote_commit_date": last_remote_commit_date
    }

def update_repo_cache(repo_path: Path):
    try:
        subprocess.run(
            ["git", "fetch", "--all", "--prune", "--quiet", "--depth=1"],
            cwd=repo_path,
            env={"GIT_TERMINAL_PROMPT": "0"}
        )
    except Exception:
        pass
    info = get_git_info(repo_path)
    if info:
        git_cache[repo_path.name] = info
        return info
    # Always return name even if fetch fails
    return {"name": repo_path.name, "error": "Could not fetch repo"}


# --- Routes ---
@app.get("/", response_class=HTMLResponse)
def dashboard():
    current_dir = Path(__file__).parent
    parent_dir = current_dir.parent
    sibling_dirs = [d for d in parent_dir.iterdir() if d.is_dir()]
    repo_names = [d.name for d in sibling_dirs]

    html = """
    <html>
    <head>
        <title>Git Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f7f7f7; }
            h1 { color: #333; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
            th { background-color: #4682B4; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            tr.outdated { background-color: #ffcccc; }
            tr.fetching td, tr.pulling td { opacity: 0.6; }
            button { border: none; padding: 5px 10px; cursor: pointer; border-radius: 4px; color: white; }
            button.fetch { background-color: #4682B4; }
            button.pull { background-color: #e94e77; }
            button:disabled { background-color: #999; cursor: not-allowed; }
            #fetch-all { margin-bottom: 10px; background-color: #5a9bd3; }
            .spinner { display:inline-block; width:16px; height:16px; border:2px solid rgba(0,0,0,0.2); border-top-color:#333; border-radius:50%; animation:spin 0.6s linear infinite; margin-left:5px; vertical-align:middle; }
            @keyframes spin { to { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
    <h1>Git Dashboard</h1>
    <button id="fetch-all">Fetch All</button>
    <table id="repo-table">
    <tr><th>Actions</th><th>Repo</th><th>Behind</th><th>Branch</th><th>Local Commit</th><th>Remote Commit</th><th>Last Local Commit</th><th>Last Remote Commit</th></tr>
    """

    for name in repo_names:
        html += f"<tr id='repo-{name}'><td colspan='8'>Loading {name}...</td></tr>"

    html += "</table>"
    html += """
    <script>
    const repoNames = [""" + ",".join(f'"{n}"' for n in repo_names) + """];
    
    function createButton(text, cls, onClick) {
        const btn = document.createElement('button');
        btn.innerText = text;
        btn.className = cls;
        btn.onclick = onClick;
        return btn;
    }

    function updateRow(row, data) {
            if(data.error) {
            const repoName = data.name || repoNameFallback; // fallback to known repo
            row.innerHTML = `<td colspan="8">${repoName}: ${data.error}</td>`;
            row.className = '';
            return;
        }

        const rowClass = data.behind > 0 ? 'outdated' : '';
        row.className = rowClass;
        row.innerHTML = '';
        const actionsTd = document.createElement('td');

        const fetchBtn = createButton('Fetch', 'fetch', async () => {
            row.classList.add('fetching');
            fetchBtn.disabled = true;
            const spinner = document.createElement('span');
            spinner.className = 'spinner';
            actionsTd.appendChild(spinner);
            const res = await fetch('/fetch_repo/' + data.name);
            const newData = await res.json();
            updateRow(row, newData);
        });
        const pullBtn = createButton('Pull', 'pull', async () => {
            row.classList.add('pulling');
            fetchBtn.disabled = true;
            pullBtn.disabled = true;
            const spinner = document.createElement('span');
            spinner.className = 'spinner';
            actionsTd.appendChild(spinner);
            const res = await fetch('/pull_repo', {
                method:'POST',
                headers:{'Content-Type':'application/x-www-form-urlencoded'},
                body: `repo_path=${encodeURIComponent(data.path)}`
            });
            const newData = await res.json();
            updateRow(row, newData);
        });

        actionsTd.appendChild(fetchBtn);
        actionsTd.appendChild(pullBtn);
        row.appendChild(actionsTd);
        row.innerHTML += `<td>${data.name}</td>
                          <td>${data.behind}</td>
                          <td>${data.branch}</td>
                          <td>${data.local_commit.substring(0,7)}</td>
                          <td>${data.remote_commit ? data.remote_commit.substring(0,7) : 'N/A'}</td>
                          <td>${data.last_local_commit_date}</td>
                          <td>${data.last_remote_commit_date}</td>`;
    }

    async function fetchRepo(repoName) {
        const row = document.getElementById('repo-' + repoName);
        row.classList.add('fetching');
        const res = await fetch('/fetch_repo/' + repoName);
        const data = await res.json();
        updateRow(row, data);
        row.classList.remove('fetching');
    }

    async function fetchAll() {
        for(const repo of repoNames) {
            fetchRepo(repo);
        }
    }

    document.getElementById('fetch-all').onclick = fetchAll;

    // Initial load
    repoNames.forEach(fetchRepo);
    </script>
    </body></html>
    """
    return HTMLResponse(html)

@app.get("/fetch_repo/{repo_name}")
def fetch_repo(repo_name: str):
    repo_path = Path(__file__).parent.parent / repo_name
    info = update_repo_cache(repo_path)
    if not info:
        return JSONResponse({"name": repo_name, "error": "Cannot fetch"})
    return JSONResponse(info)

@app.post("/pull_repo")
def pull_repo(repo_path: str = Form(...)):
    repo = Path(repo_path)
    if repo.exists() and (repo / ".git").exists():
        try:
            subprocess.run(
                ["git", "pull"],
                cwd=repo,
                stderr=subprocess.DEVNULL,
                env={"GIT_TERMINAL_PROMPT": "0"}
            )
        except subprocess.CalledProcessError:
            return JSONResponse({"name": repo.name, "error": "Pull failed"})
    info = update_repo_cache(repo)
    return JSONResponse(info)
