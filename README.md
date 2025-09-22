The goal of this project is to create a personal, automated deployment dashboard that allows you to securely deploy your own GitHub repositories to a VPS with minimal effort. More specifically, it aims to:

1. Secure Access

Only allow access to the dashboard if you are authenticated via GitHub OAuth.

Restrict access to a single whitelisted email, so only you (or specific users) can deploy apps.

2. Repo Selection & Management

List all your GitHub repositories (public and private if OAuth scopes allow).

Let you search, select, and confirm which repository to deploy.

3. Automated Deployment

Once a repo is selected and confirmed:

Clone the repository into a specific folder on your VPS.

Automatically create a Python virtual environment.

Install dependencies from requirements.txt.

Set the application port and .env variables based on the dashboard form.

Optionally start the application automatically (e.g., with uvicorn or systemd).

4. Convenience & Efficiency

Make deploying apps as simple as a few clicks in a browser.

Eliminate the need to SSH into the server, manually clone repos, or set up virtual environments.

Provide a dashboard interface for managing deployments, environment variables, and ports.

5. Optional Future Goals

Sandbox deployments using Docker for isolation and safety.

Keep a log of deployments or running applications.

Allow multiple applications to run on different ports on the same VPS.

In short:

The project is essentially a personal “deploy-any-repo” web dashboard, letting you securely deploy your own GitHub projects to your VPS in just a few clicks.