import os
import sys # Import sys to get the current Python executable
import subprocess
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Get Git credentials from environment variables
git_username = os.getenv('GIT_USERNAME')
git_password = os.getenv('GIT_PASSWORD')

# Repository information
repo_url = 'https://mygit.th-deg.de/ai-project-summer-25/llmano-2.git' # Replace with your actual repo URL if different
parsed_url = urlparse(repo_url)

# Get the script directory structure
script_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(script_dir)
repo_name = os.path.basename(parsed_url.path).replace('.git', '')
repo_path = os.path.join(parent_dir, repo_name)
requirements_path = os.path.join(repo_path, 'requirements.txt') # Path to requirements.txt

# Construct Git URL with credentials
# Ensure password characters are URL-encoded if necessary, though subprocess often handles this
git_url_with_credentials = f'https://{git_username}:{git_password}@{parsed_url.netloc}{parsed_url.path}'

# Secret token for webhook verification
SECRET_TOKEN = os.getenv('WEBHOOK_SECRET', '')  # Get from .env or leave empty


def check_requirements_changed(repo_path):
    """Checks if requirements.txt changed in the last git operation (pull/clone)."""
    # Command to check if requirements.txt differs between HEAD and the previous state (HEAD@{1})
    # This works after a pull. It won't work right after a clone (HEAD@{1} doesn't exist).
    command = ['git', 'diff', 'HEAD@{1}', 'HEAD', '--', 'requirements.txt']
    try:
        # Run the command in the repository directory
        result = subprocess.run(command, cwd=repo_path, check=True, capture_output=True, text=True)
        # If the command runs successfully and stdout is not empty, the file changed.
        if result.stdout:
            print("requirements.txt has changed.")
            return True
        else:
            print("requirements.txt has not changed.")
            return False
    except subprocess.CalledProcessError as e:
        # Handle cases where the command fails (e.g., just after clone, HEAD@{1} might not exist)
        # Or if requirements.txt wasn't tracked before.
        print(f"Could not determine changes in requirements.txt: {e.stderr}")
        # Let's check if the file exists now, maybe it was added?
        # A simpler check: does requirements.txt exist? If yes, maybe install anyway?
        # For robustness, we'll only return True if the diff command explicitly shows changes.
        return False
    except FileNotFoundError:
        # Git command not found
        print("Error: 'git' command not found. Make sure Git is installed and in the PATH.")
        return False


def install_requirements(repo_path):
    """Installs dependencies from requirements.txt."""
    pip_command = [sys.executable, '-m', 'pip', 'install', '-r', requirements_path]
    print(f"Running pip install: {' '.join(pip_command)}")
    try:
        result = subprocess.run(pip_command, check=True, capture_output=True, text=True, cwd=repo_path)
        print("pip install successful.")
        print(result.stdout)
        return True, "Pip install successful", result.stdout
    except FileNotFoundError:
        error_message = f"Error: '{sys.executable} -m pip' command not found or requirements.txt missing at {requirements_path}."
        print(error_message)
        return False, error_message, ""
    except subprocess.CalledProcessError as e:
        error_message = f"Error during pip install: {e.stderr}"
        print(error_message)
        return False, error_message, e.stderr


def git_pull():
    """Clones the repo if it doesn't exist, or pulls changes if it does.
       Installs requirements if requirements.txt changed during the pull.
       Returns a dictionary with status details."""
    
    results = {
        'status': 'success',
        'message': '',
        'output': '',
        'pip_installed': False,
        'pip_message': '',
        'pip_output': ''
    }
    
    operation_type = "" # To track if it was a clone or pull

    try:
        # Check if repository exists locally
        if not os.path.exists(repo_path):
            print(f"Repository does not exist locally. Cloning into {repo_path}...")
            command = ['git', 'clone', git_url_with_credentials, repo_path]
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            results['message'] = "Repository cloned successfully"
            results['output'] = result.stdout
            operation_type = "clone"
            # After cloning, install requirements if requirements.txt exists
            if os.path.exists(requirements_path):
                 print("Running initial pip install after clone...")
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
            print(f"Repository exists at {repo_path}. Performing git pull...")
            # Store current HEAD hash to compare later (alternative to git diff HEAD@{1})
            # current_head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo_path, capture_output=True, text=True, check=True).stdout.strip()

            command = ['git', 'pull']
            result = subprocess.run(command, check=True, capture_output=True, text=True, cwd=repo_path)
            results['message'] = "Git pull executed successfully"
            results['output'] = result.stdout
            operation_type = "pull"

            # Check if requirements.txt changed *only after a pull*
            if operation_type == "pull":
                print("Checking if requirements.txt changed...")
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
        error_message = f"Error during git operation ({operation_type}): {e.stderr}"
        print(error_message)
        results['status'] = 'error'
        results['message'] = error_message
        results['output'] = e.stderr # Store stderr in output on error
    except Exception as e:
        # Catch other potential errors
        error_message = f"An unexpected error occurred: {str(e)}"
        print(error_message)
        results['status'] = 'error'
        results['message'] = error_message

    return results


@app.route('/', methods=['GET'])
def index():
    # Optional: Maybe you don't want to pull+install on every GET request?
    # Consider just returning a status message or removing this route.
    pull_results = git_pull()
    return jsonify(pull_results), 200 if pull_results['status'] == 'success' else 500


@app.route('/webhook', methods=['POST'])
def webhook():
    # Verify the token if set
    if SECRET_TOKEN:
        gitlab_token = request.headers.get('X-Gitlab-Token')
        if not gitlab_token or gitlab_token != SECRET_TOKEN:
            print("Webhook Error: Invalid or missing X-Gitlab-Token")
            return jsonify({'status': 'error', 'message': 'Invalid token'}), 401
        else:
             print("Webhook token verified.")

    # Get the event type
    event_type = request.headers.get('X-Gitlab-Event')
    print(f"Received Gitlab event: {event_type}")

    # Process push events
    if event_type == 'Push Hook':
        # Check the payload for branch if needed (e.g., only pull for 'main' branch)
        # data = request.get_json()
        # print(f"Push event details: {data.get('ref', 'No ref found')}")
        # if data.get('ref') != 'refs/heads/main': # Example: only trigger for main branch
        #    print("Push event not for main branch, ignoring.")
        #    return jsonify({'status': 'ignored', 'message': 'Push not to main branch'})

        print("Processing push hook...")
        pull_results = git_pull()

        # Log the result
        print(f"Git pull & requirement check results: {pull_results}")

        return jsonify(pull_results), 200 if pull_results['status'] == 'success' else 500

    else:
        print(f"Ignoring event type: {event_type}")
        return jsonify({'status': 'ignored', 'message': f'Event type {event_type} not processed'})

if __name__ == '__main__':
    # Check if credentials are available
    if not git_username or not git_password:
        print("Warning: Git credentials not found in .env file. Webhook may fail for private repositories.")
    
    # Check if repo path is writable if it exists
    if os.path.exists(repo_path) and not os.access(repo_path, os.W_OK):
         print(f"Warning: Repository path {repo_path} exists but might not be writable by the script user.")

    # Ensure parent directory exists and is writable for cloning
    if not os.path.exists(parent_dir):
        try:
            os.makedirs(parent_dir)
            print(f"Created parent directory: {parent_dir}")
        except OSError as e:
             print(f"Error: Could not create parent directory {parent_dir}. Check permissions. Error: {e}")
             sys.exit(1) # Exit if we can't create the directory where the repo should be cloned
    elif not os.access(parent_dir, os.W_OK):
        print(f"Error: Parent directory {parent_dir} exists but is not writable. Check permissions.")
        sys.exit(1) # Exit if we can't write where the repo should be cloned


    # Run the Flask app
    print(f"Starting webhook server for repository: {repo_name}")
    print(f"Repository path: {repo_path}")
    print(f"Listening on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001) # Removed debug=True for production-like environment