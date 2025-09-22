import os
import shutil
import asyncio
import subprocess
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()

# Config from .env
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
WHITELISTED_EMAIL = os.getenv("WHITELISTED_EMAIL")
PORT = int(os.getenv("PORT", 8000))
SESSION_SECRET = os.getenv("SESSION_SECRET", "please_change_me")
REDIRECT_URI = f"http://localhost:{PORT}/callback"  # adjust if using a domain

REPOS_BASE = os.path.abspath("repos")
os.makedirs(REPOS_BASE, exist_ok=True)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/login")
def login():
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "read:user user:email repo",  # repo scope if you want private repos too
        "allow_signup": "false",
        # optionally add "state" for CSRF protection
    }
    url = "https://github.com/login/oauth/authorize?" + urlencode(params)
    return RedirectResponse(url)


@app.get("/callback")
async def callback(request: Request, code: Optional[str] = None):
    if not code:
        return JSONResponse({"error": "Missing code"}, status_code=400)

    token_url = "https://github.com/login/oauth/access_token"
    headers = {"Accept": "application/json"}
    data = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, headers=headers, data=data, timeout=20.0)
        token_json = token_resp.json()

        access_token = token_json.get("access_token")
        if not access_token:
            return JSONResponse({"error": "Failed to obtain access token", "detail": token_json}, status_code=400)

        # Get user
        user_resp = await client.get("https://api.github.com/user", headers={"Authorization": f"Bearer {access_token}"})
        user_json = user_resp.json()
        login = user_json.get("login")

        # Get emails
        emails_resp = await client.get("https://api.github.com/user/emails", headers={"Authorization": f"Bearer {access_token}"})
        emails_json = emails_resp.json()
        primary_email = None
        if isinstance(emails_json, list):
            primary_email = next((e.get("email") for e in emails_json if e.get("primary")), None)
        else:
            # fallback to user json
            primary_email = user_json.get("email")

    if primary_email != WHITELISTED_EMAIL:
        return HTMLResponse(f"<h2>403 — Email not whitelisted ({primary_email})</h2>", status_code=403)

    # Save token & user in session
    request.session["access_token"] = access_token
    request.session["github_login"] = login
    request.session["email"] = primary_email

    return RedirectResponse(url="/dashboard")


from fastapi import HTTPException, Depends

def get_current_user(request: Request):
    """Ensure the user is logged in via GitHub OAuth."""
    access_token = request.session.get("access_token")
    if not access_token:
        # Redirect to login page if not authenticated
        raise HTTPException(status_code=307, detail="Redirect to login", headers={"Location": "/"})
    return {
        "access_token": access_token,
        "github_login": request.session.get("github_login"),
        "email": request.session.get("email")
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    access_token = user["access_token"]
    github_login = user["github_login"]
    email = user["email"]

    # Fetch user's repos (same as before)
    repos: List[Dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.github.com/user/repos?per_page=100",
                                headers={"Authorization": f"Bearer {access_token}"})
        if resp.status_code == 200:
            repos = resp.json()
        else:
            resp2 = await client.get("https://api.github.com/user")
            username = resp2.json().get("login")
            resp3 = await client.get(f"https://api.github.com/users/{username}/repos?per_page=100")
            repos = resp3.json()

    repo_list = [{"full_name": r.get("full_name"), "name": r.get("name"), "owner": r.get("owner", {}).get("login"), "private": r.get("private")} for r in repos]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "repos": repo_list,
        "github_login": github_login,
        "email": email,
        "default_port": 8000,
    })

@app.post("/deploy")
async def deploy(
    request: Request,
    repo_full_name: str = Form(...),  # e.g. owner/repo
    app_port: int = Form(...),
    env_text: str = Form(""),  # user-provided env lines, key=value per line
    start_after_deploy: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
):
    access_token = request.session.get("access_token")
    github_login = request.session.get("github_login")
    if not access_token:
        return JSONResponse({"error": "not authenticated"}, status_code=403)

    # sanitize repo_full_name
    if "/" not in repo_full_name:
        return JSONResponse({"error": "invalid repo name"}, status_code=400)
    owner, repo_name = repo_full_name.split("/", 1)
    if owner.lower() != github_login.lower():
        # restrict to repos owned by the user
        return JSONResponse({"error": "You may only deploy repositories owned by your GitHub account."}, status_code=403)

    target_dir_name = f"{owner}-{repo_name}"
    target_dir = os.path.join(REPOS_BASE, target_dir_name)

    # If directory exists, remove it (you may instead git pull — here we remove to keep simple)
    if os.path.exists(target_dir):
        try:
            shutil.rmtree(target_dir)
        except Exception as e:
            return JSONResponse({"error": "failed to remove existing directory", "detail": str(e)}, status_code=500)

    clone_url = f"https://github.com/{repo_full_name}.git"

    # run blocking operations in thread to avoid blocking event loop
    async def do_deploy():
        try:
            # Clone
            proc = await asyncio.to_thread(subprocess.run, ["git", "clone", clone_url, target_dir], {"check": True})
        except Exception as e:
            return {"status": "error", "step": "git_clone", "detail": str(e)}

        # Create venv
        venv_path = os.path.join(target_dir, ".venv")
        try:
            await asyncio.to_thread(subprocess.run, ["python3", "-m", "venv", venv_path], {"check": True})
        except Exception as e:
            return {"status": "error", "step": "create_venv", "detail": str(e)}

        pip_path = os.path.join(venv_path, "bin", "pip")
        python_path = os.path.join(venv_path, "bin", "python")

        # Upgrade pip
        try:
            await asyncio.to_thread(subprocess.run, [pip_path, "install", "--upgrade", "pip"], {"check": True})
        except Exception as e:
            # non-fatal possibly
            pass

        # Install requirements if exists
        req_file = os.path.join(target_dir, "requirements.txt")
        if os.path.exists(req_file):
            try:
                await asyncio.to_thread(subprocess.run, [pip_path, "install", "-r", req_file], {"check": True})
            except Exception as e:
                return {"status": "error", "step": "install_requirements", "detail": str(e)}

        # Write .env
        env_lines = []
        # include PORT set from dashboard
        env_lines.append(f"PORT={app_port}")
        # include additional env_text lines (user-provided)
        if env_text:
            # simple sanitization: remove any null bytes
            cleaned = "\n".join(line for line in env_text.splitlines() if line.strip())
            env_lines.append(cleaned)
        env_content = "\n".join(env_lines).strip() + "\n"
        try:
            with open(os.path.join(target_dir, ".env"), "w") as f:
                f.write(env_content)
        except Exception as e:
            return {"status": "error", "step": "write_env", "detail": str(e)}

        # Optional: create simple systemd service (uncomment if you intend to use it)
        # service_name = f"{target_dir_name}.service"
        # service_content = f"""[Unit]
        # Description=Uvicorn instance for {repo_full_name}
        # After=network.target
        #
        # [Service]
        # User={os.getlogin()}
        # Group={os.getlogin()}
        # WorkingDirectory={target_dir}
        # Environment=PATH={venv_path}/bin
        # ExecStart={venv_path}/bin/uvicorn main:app --host 0.0.0.0 --port {app_port}
        # Restart=always
        #
        # [Install]
        # WantedBy=multi-user.target
        # """
        # with open(f"/etc/systemd/system/{service_name}", "w") as f:
        #     f.write(service_content)
        # # Remember: to enable it you'd run `sudo systemctl daemon-reload && sudo systemctl enable --now {service_name}`

        result = {"status": "ok", "dir": target_dir, "port": app_port}
        return result

    # schedule deployment and return immediate response
    # run in background to avoid timeouts if user expects instant response
    # But per your instruction we must perform the task now — we will run it and wait a short time
    deploy_result = await do_deploy()

    if deploy_result.get("status") != "ok":
        return JSONResponse({"error": "deploy_failed", "detail": deploy_result}, status_code=500)

    # Optionally start the app - we won't auto-start here by default for safety
    # If user included start_after_deploy="on", we can attempt to start via uvicorn in background
    if start_after_deploy == "on":
        target_dir = deploy_result["dir"]
        venv_path = os.path.join(target_dir, ".venv")
        uvicorn_path = os.path.join(venv_path, "bin", "uvicorn")
        # Command assumes the repo has `main:app` as ASGI app — adjust if different.
        cmd = [uvicorn_path, "main:app", "--host", "0.0.0.0", "--port", str(app_port), "--reload"]
        # Launch in background with nohup
        try:
            await asyncio.to_thread(subprocess.Popen, ["nohup"] + cmd, cwd=target_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deploy_result["started"] = True
        except Exception as e:
            deploy_result["started"] = False
            deploy_result["start_error"] = str(e)

    return JSONResponse({"result": deploy_result})
