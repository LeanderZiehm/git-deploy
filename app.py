import os
import sys
import subprocess
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import time
import logging
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Get Git credentials from environment variables
git_username = os.getenv('GIT_USERNAME')
git_password = os.getenv('GIT_PASSWORD')

# Secret token for webhook verification
SECRET_TOKEN = os.getenv('WEBHOOK_SECRET', '')

# Get the script directory structure
script_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(script_dir)


def get_all_git_repos():
    """
    Find all Git repositories in the parent directory except the script's directory.
    Returns a list of dictionaries with repo_path and repo_name.
    """
    repos = []
    
    # Skip if parent directory doesn't exist
    if not os.path.exists(parent_dir):
        logger.warning(f"Parent directory {parent_dir} doesn't exist")
        return repos
        
    # List all items in the parent directory
    for item in os.listdir(parent_dir):
        item_path = os.path.join(parent_dir, item)
        
        # Skip if it's not a directory or if it's the script's directory
        if not os.path.isdir(item_path) or item_path == script_dir:
            continue
            
        # Check if the directory contains a .git folder
        git_dir = os.path.join(item_path, '.git')
        if os.path.exists(git_dir) and os.path.isdir(git_dir):
            repos.append({
                'repo_path': item_path,
                'repo_name': item
            })
            
    logger.info(f"Found {len(repos)} Git repositories in {parent_dir}")
    for repo in repos:
        logger.info(f"- {repo['repo_name']} at {repo['repo_path']}")
        
    return repos


def check_requirements_changed(repo_path):
    """Checks if requirements.txt changed in the last git operation (pull)."""
    # Command to check if requirements.txt differs between HEAD and the previous state (HEAD@{1})
    command = ['git', 'diff', 'HEAD@{1}', 'HEAD', '--', 'requirements.txt']
    try:
        # Run the command in the repository directory
        result = subprocess.run(command, cwd=repo_path, check=True, capture_output=True, text=True)
        # If the command runs successfully and stdout is not empty, the file changed.
        if result.stdout:
            logger.info(f"requirements.txt has changed in {os.path.basename(repo_path)}")
            return True
        else:
            logger.info(f"requirements.txt has not changed in {os.path.basename(repo_path)}")
            return False
    except subprocess.CalledProcessError as e:
        # Handle cases where the command fails (e.g., just after clone, HEAD@{1} might not exist)
        logger.warning(f"Could not determine changes in requirements.txt for {os.path.basename(repo_path)}: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("Error: 'git' command not found. Make sure Git is installed and in the PATH.")
        return False


def install_requirements(repo_path):
    """Installs dependencies from requirements.txt if it exists."""
    requirements_path = os.path.join(repo_path, 'requirements.txt')
    
    # Check if requirements.txt exists
    if not os.path.exists(requirements_path):
        logger.info(f"No requirements.txt found in {os.path.basename(repo_path)}")
        return False, "No requirements.txt found", ""
    
    # Install requirements
    pip_command = [sys.executable, '-m', 'pip', 'install', '-r', requirements_path]
    logger.info(f"Running pip install in {os.path.basename(repo_path)}: {' '.join(pip_command)}")
    
    try:
        result = subprocess.run(pip_command, check=True, capture_output=True, text=True, cwd=repo_path)
        logger.info(f"pip install successful for {os.path.basename(repo_path)}")
        return True, "Pip install successful", result.stdout
    except FileNotFoundError:
        error_message = f"Error: '{sys.executable} -m pip' command not found"
        logger.error(error_message)
        return False, error_message, ""
    except subprocess.CalledProcessError as e:
        error_message = f"Error during pip install: {e.stderr}"
        logger.error(error_message)
        return False, error_message, e.stderr


def git_pull_repo(repo_path, repo_name):
    """
    Pulls changes for an existing repository and handles requirements.
    Returns a dictionary with status details.
    """
    results = {
        'repo_name': repo_name,
        'status': 'success',
        'message': '',
        'output': '',
        'pip_installed': False,
        'pip_message': '',
        'pip_output': ''
    }
    
    try:
        logger.info(f"Performing git pull for {repo_name}...")
        command = ['git', 'pull']
        result = subprocess.run(command, check=True, capture_output=True, text=True, cwd=repo_path)
        results['message'] = "Git pull executed successfully"
        results['output'] = result.stdout
        
        # Check if requirements.txt changed
        logger.info(f"Checking if requirements.txt changed in {repo_name}...")
        if check_requirements_changed(repo_path):
            pip_success, pip_msg, pip_out = install_requirements(repo_path)
            results['pip_installed'] = pip_success
            results['pip_message'] = pip_msg
            results['pip_output'] = pip_out
            if not pip_success:
                # Elevate status to error if pip install fails
                results['status'] = 'error'
                # Prepend pip error message
                results['message'] = f"{pip_msg}. " + results['message']
        else:
            results['pip_message'] = "requirements.txt did not change, skipping pip install."
            
    except subprocess.CalledProcessError as e:
        error_message = f"Error during git pull: {e.stderr}"
        logger.error(error_message)
        results['status'] = 'error'
        results['message'] = error_message
        results['output'] = e.stderr
    except Exception as e:
        error_message = f"An unexpected error occurred: {str(e)}"
        logger.error(error_message)
        results['status'] = 'error'
        results['message'] = error_message
        
    return results


def process_all_repos():
    """
    Process all Git repositories found in the parent directory.
    Returns a list of status results for each repository.
    """
    all_results = []
    repos = get_all_git_repos()
    
    for repo in repos:
        repo_path = repo['repo_path']
        repo_name = repo['repo_name']
        
        # Pull changes and process requirements
        repo_results = git_pull_repo(repo_path, repo_name)
        all_results.append(repo_results)
        
    return all_results


@app.route('/', methods=['GET'])
def index():
    """Return status of all repositories on GET request."""
    results = process_all_repos()
    overall_status = 200
    
    # If any repo has an error, return 500
    for result in results:
        if result['status'] == 'error':
            overall_status = 500
            break
            
    return jsonify(results), overall_status


@app.route('/webhook', methods=['POST'])
def webhook():
    """Process webhook requests for repositories."""
    # Verify the token if set
    if SECRET_TOKEN:
        gitlab_token = request.headers.get('X-Gitlab-Token')
        if not gitlab_token or gitlab_token != SECRET_TOKEN:
            logger.warning("Webhook Error: Invalid or missing X-Gitlab-Token")
            return jsonify({'status': 'error', 'message': 'Invalid token'}), 401
        else:
            logger.info("Webhook token verified.")

    # Get the event type
    event_type = request.headers.get('X-Gitlab-Event')
    logger.info(f"Received Gitlab event: {event_type}")

    # Process push events
    if event_type == 'Push Hook':
        logger.info("Processing push hook...")
        data = request.get_json()
        
        # Extract repository information from the webhook payload
        try:
            repo_url = data.get('repository', {}).get('git_http_url', '')
            repo_name = data.get('repository', {}).get('name', '')
            
            # Find which local repo corresponds to this webhook
            repos = get_all_git_repos()
            target_repo = None
            
            for repo in repos:
                # Try to get the remote URL of this repo
                try:
                    cmd = ['git', 'config', '--get', 'remote.origin.url']
                    remote_url = subprocess.run(cmd, cwd=repo['repo_path'], 
                                               capture_output=True, text=True, check=True).stdout.strip()
                    
                    # Compare URLs (normalize by removing credentials and .git suffix)
                    parsed_remote = urlparse(remote_url)
                    parsed_webhook = urlparse(repo_url)
                    
                    if parsed_remote.netloc == parsed_webhook.netloc and parsed_remote.path.rstrip('.git') == parsed_webhook.path.rstrip('.git'):
                        target_repo = repo
                        break
                except:
                    continue
            
            if target_repo:
                # Process only the specific repository that triggered the webhook
                result = git_pull_repo(target_repo['repo_path'], target_repo['repo_name'])
                return jsonify(result), 200 if result['status'] == 'success' else 500
            else:
                # If we can't find the specific repo, process all repos
                logger.warning(f"Could not find local repository for {repo_url}, processing all repos")
                results = process_all_repos()
                overall_status = 200
                for result in results:
                    if result['status'] == 'error':
                        overall_status = 500
                        break
                return jsonify(results), overall_status
                
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            # Fall back to processing all repos if there's an error
            results = process_all_repos()
            return jsonify(results), 500

    else:
        logger.info(f"Ignoring event type: {event_type}")
        return jsonify({'status': 'ignored', 'message': f'Event type {event_type} not processed'})


if __name__ == '__main__':
    # Check if credentials are available
    if not git_username or not git_password:
        logger.warning("Git credentials not found in .env file. Webhook may fail for private repositories.")
    
    # Ensure parent directory exists
    if not os.path.exists(parent_dir):
        logger.error(f"Parent directory {parent_dir} doesn't exist")
        sys.exit(1)
    
    # Initial check and processing of all repositories
    logger.info("Performing initial check of all repositories...")
    process_all_repos()

    # Run the Flask app
    logger.info(f"Starting webhook server for multiple repositories")
    logger.info(f"Monitoring parent directory: {parent_dir}")
    logger.info(f"Listening on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001)
