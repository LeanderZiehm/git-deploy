from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import subprocess
from pathlib import Path

app = FastAPI(title="Git Dashboard")


def run_git(cmd, repo_path: Path):
    """Run git command safely without prompting for credentials."""
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
    """Return detailed git info for a repo, or None if inaccessible."""
    if not (repo_path / ".git").exists():
        return None

    subprocess.run(
        ["git", "fetch"],
        cwd=repo_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"GIT_TERMINAL_PROMPT": "0"}
    )

    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
    local_commit = run_git(["rev-parse", "HEAD"], repo_path)
    remote_commit = run_git(["rev-parse", f"origin/{branch}"], repo_path) if branch else None

    if not branch or not local_commit:
        return None

    ahead_behind = run_git(["rev-list", "--left-right", "--count", f"{branch}...origin/{branch}"], repo_path)
    last_local_commit_date = run_git(["log", "-1", "--format=%ci", branch], repo_path)
    last_remote_commit_date = run_git(["log", "-1", "--format=%ci", f"origin/{branch}"], repo_path) if remote_commit else None

    ahead, behind = (0, 0)
    if ahead_behind:
        ahead, behind = map(int, ahead_behind.split())

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


# --- Lightweight initial dashboard ---
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
        <script defer src="https://umami.leanderziehm.com/script.js" data-website-id="66e46def-18be-4149-8bde-c9dab2b84208"></script>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f7f7f7; }
            h1 { color: #333; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
            th { background-color: #4682B4; color: white; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            tr.outdated { background-color: #ffe6e6; }
            button { background-color: #4682B4; color: white; border: none; padding: 5px 10px; cursor: pointer; }
            button:hover { background-color: #5a9bd3; }
        </style>
    </head>
    <body>
    <h1>Git Dashboard</h1>
    <table id="repo-table">
    <tr><th>Actions</th><th>Repo</th><th>Behind</th><th>Branch</th><th>Local Commit</th><th>Remote Commit</th><th>Last Local Commit</th><th>Last Remote Commit</th></tr>
    """

    # Initially just render rows with "Loading..."
    for name in repo_names:
        html += f"<tr id='repo-{name}'>"
        html += f"<td colspan='8'>Loading {name}...</td>"
        html += "</tr>"

    html += "</table>"

    # JavaScript to fetch detailed info asynchronously
    html += """
    <script>
    async function fetchRepoInfo(repoName) {
        try {
            const res = await fetch('/repo_info/' + repoName);
            const data = await res.json();
            const row = document.getElementById('repo-' + repoName);
            if (data.error) {
                row.innerHTML = `<td colspan="8">${repoName}: ${data.error}</td>`;
                return;
            }
            const rowClass = data.behind > 0 ? 'outdated' : '';
            row.className = rowClass;
            row.innerHTML = `
                <td><form method="post" action="/pull">
                    <input type="hidden" name="repo_path" value="${data.path}">
                    <button type="submit">Pull</button>
                </form></td>
                <td>${data.name}</td>
                <td>${data.behind}</td>
                <td>${data.branch}</td>
                <td>${data.local_commit.substring(0,7)}</td>
                <td>${data.remote_commit ? data.remote_commit.substring(0,7) : 'N/A'}</td>
                <td>${data.last_local_commit_date}</td>
                <td>${data.last_remote_commit_date}</td>
            `;
        } catch (err) {
            console.error('Failed to fetch info for', repoName, err);
        }
    }

    // Load each repo info in the background
    const repoNames = [""" + ",".join(f'"{n}"' for n in repo_names) + """];
    repoNames.forEach(fetchRepoInfo);
    </script>
    """

    html += "</body></html>"
    return HTMLResponse(html)


# --- Endpoint to fetch detailed info asynchronously ---
@app.get("/repo_info/{repo_name}")
def repo_info(repo_name: str):
    repo_path = Path(__file__).parent.parent / repo_name
    info = get_git_info(repo_path)
    if info:
        return JSONResponse(info)
    return JSONResponse({"name": repo_name, "error": "No access"})


# --- Pull action ---
@app.post("/pull")
def pull_repo(repo_path: str = Form(...)):
    repo = Path(repo_path)
    if repo.exists() and (repo / ".git").exists():
        try:
            subprocess.check_output(
                ["git", "pull"],
                cwd=repo,
                stderr=subprocess.DEVNULL,
                env={"GIT_TERMINAL_PROMPT": "0"}
            )
        except subprocess.CalledProcessError as e:
            print(f"Failed to pull {repo}: {e}")
    return RedirectResponse("/", status_code=303)
