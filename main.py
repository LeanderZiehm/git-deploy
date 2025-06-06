# main.py
"""
Flask webhook server with auto-rollback, dependency install, and basic UI.
"""
import os
import sys
import subprocess
import logging
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import argparse
# import hotreloader

# Logging config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load env\ nload_dotenv()
SECRET_TOKEN = os.getenv('WEBHOOK_SECRET', '')

# Script/parent directory
script_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(script_dir)

app = Flask(__name__)

# In-memory state for UI
state = {
    'last_run': None,
    'repos': []  # list of dicts: name, broken, rollbacks, commit_hash, commit_count
}

def get_repos():
    repos = []
    if not os.path.isdir(parent_dir):
        return repos
    for name in os.listdir(parent_dir):
        path = os.path.join(parent_dir, name)
        if path == script_dir or not os.path.isdir(path):
            continue
        if os.path.isdir(os.path.join(path, '.git')):
            repos.append((name, path))
    return repos


def requirements_changed(repo_path: str) -> bool:
    req = os.path.join(repo_path, 'requirements.txt')
    if not os.path.isfile(req):
        return False
    diff = subprocess.run(
        ['git', 'diff', 'HEAD~1', 'HEAD', '--', 'requirements.txt'],
        cwd=repo_path, capture_output=True, text=True
    )
    return bool(diff.stdout)


def install_requirements(repo_path: str) -> None:
    req = os.path.join(repo_path, 'requirements.txt')
    if os.path.isfile(req):
        logger.info(f"Installing dependencies for {repo_path}")
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req], cwd=repo_path)

def health_check(repo_path: str) -> bool:
    """
    Walks through all .py files under repo_path and attempts to compile them.
    Returns True if all files compile without errors, False otherwise.
    """
    logging.info(f"Running health check on {repo_path}")
    for root, _, files in os.walk(repo_path):
        for fname in files:
            if fname.endswith('.py'):
                file_path = os.path.join(root, fname)
                result = subprocess.run([
                    sys.executable, '-m', 'py_compile', file_path
                ], capture_output=True, text=True)
                if result.returncode != 0:
                    logging.error(f"Syntax error in {file_path}: {result.stderr.strip()}")
                    return False
    logging.info("Health check passed: all Python files compile")
    return True


def rollback_until_green(repo_path: str) -> int:
    """Returns number of rollbacks performed."""
    count = 0
    if requirements_changed(repo_path):
        install_requirements(repo_path)
    while True:
        if health_check(repo_path):
            break
        # check if we can go back one more commit
        ret = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD~1'], cwd=repo_path)
        if ret.returncode != 0:
            logger.error(f"No more commits to roll back in {repo_path}")
            break
        logger.warning(f"Rolling back one commit in {repo_path}")
        subprocess.run(['git', 'reset', '--hard', 'HEAD~1'], cwd=repo_path)
        count += 1
    return count


def get_commit_info(repo_path: str) -> (str, int):
    """Returns (short hash, commit count)."""
    h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=repo_path, capture_output=True, text=True)
    c = subprocess.run(['git', 'rev-list', '--count', 'HEAD'], cwd=repo_path, capture_output=True, text=True)
    return h.stdout.strip(), int(c.stdout.strip())


def pull_and_check(name: str, path: str) -> dict:
    res = {'name': name, 'broken': False, 'rollbacks': 0}
    try:
        logger.info(f"Pulling {name}")
        subprocess.run(['git', 'pull'], cwd=path, check=True, capture_output=True, text=True)
        count = rollback_until_green(path)
        res['rollbacks'] = count
        res['broken'] = (count > 0)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error pulling {name}: {e.stderr}")
        res['broken'] = True
    # commit info
    h, c = get_commit_info(path)
    res['commit_hash'] = h
    res['commit_count'] = c
    return res


def process_all():
    results = []
    for name, path in get_repos():
        results.append(pull_and_check(name, path))
    # own repo
    self_name = os.path.basename(script_dir)
    results.append(pull_and_check(self_name, script_dir))
    state['last_run'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    state['repos'] = results
    return results

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'last_run': state['last_run'],
        'repos': state['repos']
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    if SECRET_TOKEN:
        token = request.headers.get('X-Webhook-Token', '')
        if token != SECRET_TOKEN:
            return jsonify({'status': 'error', 'message': 'Invalid token'}), 401
    thread = threading.Thread(target=process_all)
    thread.start()
    return jsonify({'status': 'started'})

@app.route('/kinnari')
def kinnari():
    return "kinnari"



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Webhook server for Git repositories")
    parser.add_argument('--port', type=int, default=5005, help='Port number to run the server on (default: 5005)')
    args = parser.parse_args()
    port = args.port
    # initial load
    process_all()
    logger.info(f"Listening on http://0.0.0.0:{port}")
    # app.run(host='0.0.0.0', port=port)
    app.run(host='0.0.0.0', port=port,debug=True,use_reloader=True)
