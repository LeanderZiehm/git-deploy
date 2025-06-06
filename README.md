# 🚀 git-deploy

**A lightweight, fast, and secure self-hosted GitOps deployment tool.**  
Minimal dependencies, maximum control — ideal for low-resource servers.

---

## 🌐 Overview

`git-deploy` is an open-source alternative to platforms like **Vercel**, **Coolify**, and **Render**, built for:

- 🧠 Developers who want **simple automation** over fancy dashboards.
- 🪶 Lightweight and **low-resource** environments (e.g. VPS, Raspberry Pi).
- 🔒 Security-minded users who want full **local control** of deployment logic.
- 🧰 Anyone tired of bloated, over-complicated CI/CD tools.

It listens for Git push events (e.g. from GitLab or GitHub), pulls updated code, and runs `pip install` automatically **only if** `requirements.txt` changes.

---

## ⚙️ Features

- ✅ **Zero-config deployment**: Drop it next to your projects and go.
- 🐍 Python-based, powered by **Flask**, with only standard libraries and `python-dotenv`.
- 🔧 Supports **multiple Git repos** with auto-discovery.
- 🔐 Verifies webhook secrets.
- 💾 Only installs dependencies if `requirements.txt` changed.
- 🪶 **No database**, **no Docker**, no Nginx or systemd required.
- 🔄 Works with **GitLab Webhooks**, supports GitHub with minor tweaks.

---

## 🏁 Quick Start

### 1. 🔧 Setup

Install Python 3.7+ and Git on your server.

```bash
git clone https://github.com/yourusername/git-deploy.git
cd git-deploy
pip install -r requirements.txt
````

Create a `.env` file:

```dotenv
GIT_USERNAME=your-username
GIT_PASSWORD=your-token-or-password
WEBHOOK_SECRET=your-secret-token
```

> Make sure all your project repos live in the **parent directory** of this script.

### 2. 🚀 Run It

```bash
python main.py
```

By default, it will:

* Scan all sibling directories for Git repositories
* Pull the latest changes
* Install dependencies only if needed
* Start a Flask server on `http://0.0.0.0:5005`

---

## 📡 Webhook Integration

### GitLab

1. Go to your repo → **Settings → Webhooks**
2. URL: `http://your-server-ip:5005/webhook`
3. Secret Token: same as `WEBHOOK_SECRET` in `.env`
4. Trigger on: **Push events**
5. Save

---

## 📁 Directory Structure

```
parent-folder/
├── repo1/
│   └── .git/
├── repo2/
│   └── .git/
└── git-deploy/
    ├── main.py
    ├── .env
    └── ...
```

---

## 🔐 Security Notes

* Keep `.env` protected and outside of version control.
* For HTTPS, use a reverse proxy like Caddy, Nginx, or Cloudflare Tunnel.

---

## 🧠 Philosophy

`git-deploy` was built because:

* You **don’t** need Docker and Kubernetes for everything.
* CI/CD should be **declarative and simple**, not another devops job.
* Resource-constrained devices still deserve good DX.

---

## ❓ FAQ

**Q: Does it support GitHub?**
A: Not out of the box, but you can modify the webhook handler easily.

**Q: Can I trigger a script after deploy?**
A: Yes! Add logic in `git_pull_repo()` to run any custom post-pull commands.

**Q: Does it work with private repos?**
A: Yes, ensure your `.env` has valid `GIT_USERNAME` and `GIT_PASSWORD` (or a personal access token).

---

## 🛠️ Roadmap

* [ ] GitHub webhook support
* [ ] Custom post-deploy scripts per repo
* [ ] Web UI (minimal)
* [ ] Auto TLS via reverse proxy helper

---

## 📜 License

[MIT](LICENSE)

---

## 🙌 Contributing

PRs and issues welcome! If you use this in production, consider starring 🌟 the repo.

---

Let me know if you'd like:
- A logo/banner
- Systemd service config
- Dockerfile (optional, for those who *do* want it)

- GitHub Actions to deploy this itself

Let’s make `git-deploy` lean, powerful, and community-loved.
