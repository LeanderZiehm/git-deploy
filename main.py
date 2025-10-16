from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import subprocess
import os
from pathlib import Path

app = FastAPI(title="Git Dashboard")

def run_git(cmd):
    try:
        return subprocess.check_output(
            ["git"] + cmd, cwd=repo_path, stderr=subprocess.DEVNULL, env={"GIT_TERMINAL_PROMPT": "0"}
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None


def get_git_info(repo_path: Path):
    if not (repo_path / ".git").exists():
        return None

    # Make sure remote refs are up to date
    subprocess.run(
        ["git", "fetch"], 
        cwd=repo_path, 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL, 
        env={"GIT_TERMINAL_PROMPT": "0"}
    )

    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    local_commit = run_git(["rev-parse", "HEAD"])
    remote_commit = run_git(["rev-parse", "origin/" + branch]) if branch else None

    if not branch or not local_commit:
        return None  # skip inaccessible repo

    ahead_behind = run_git(["rev-list", "--left-right", "--count", f"{branch}...origin/{branch}"])
    last_local_commit_date = run_git(["log", "-1", "--format=%ci", branch])
    last_remote_commit_date = run_git(["log", "-1", "--format=%ci", f"origin/{branch}"]) if remote_commit else None

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


@app.get("/", response_class=HTMLResponse)
def dashboard():
    current_dir = Path(__file__).parent
    parent_dir = current_dir.parent
    sibling_dirs = [d for d in parent_dir.iterdir() if d.is_dir()]

    repos_info = []
    for d in sibling_dirs:
        info = get_git_info(d)
        if info:
            repos_info.append(info)

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
        tr.outdated { background-color: #ffe6e6; } /* light red for outdated repos */
        button { background-color: #4682B4; color: white; border: none; padding: 5px 10px; cursor: pointer; }
        button:hover { background-color: #5a9bd3; }
    </style>
    </head>
    <body>
    <h1>Git Dashboard</h1>
    <table>
    <tr><th>Actions</th><th>Repo</th><th>Behind</th><th>Branch</th><th>Local Commit</th><th>Remote Commit</th><th>Last Local Commit</th><th>Last Remote Commit</th></tr>
    """

    for repo in repos_info:
        row_class = "outdated" if repo["behind"] > 0 else ""
        html += f"<tr class='{row_class}'>"
        html += f"<td><form method='post' action='/pull'><input type='hidden' name='repo_path' value='{repo['path']}'><button type='submit'>Pull</button></form></td>"
        html += f"<td>{repo['name']}</td>"
        html += f"<td>{repo['behind']}</td>"
        html += f"<td>{repo['branch']}</td>"
        html += f"<td>{repo['local_commit'][:7]}</td>"
        html += f"<td>{repo['remote_commit'][:7] if repo['remote_commit'] else 'N/A'}</td>"
        html += f"<td>{repo['last_local_commit_date']}</td>"
        html += f"<td>{repo['last_remote_commit_date']}</td>"

        html += f"</tr>"

    html += "</table></body></html>"
    return HTMLResponse(content=html)

@app.post("/pull")
def pull_repo(repo_path: str = Form(...)):
    repo = Path(repo_path)
    if repo.exists() and (repo / ".git").exists():
        try:
            subprocess.check_output(["git", "pull"], cwd=repo)
        except subprocess.CalledProcessError as e:
            print(f"Failed to pull {repo}: {e}")
    return RedirectResponse("/", status_code=303)
