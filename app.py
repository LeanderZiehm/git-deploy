import os
import subprocess
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Get Git credentials from environment variables (same as your original script)
git_username = os.getenv('GIT_USERNAME')
git_password = os.getenv('GIT_PASSWORD')

# Repository information from your original script
repo_url = 'https://mygit.th-deg.de/ai-project-summer-25/llmano-2.git'
parsed_url = urlparse(repo_url)

# Get the script directory structure
script_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.dirname(script_dir)
repo_name = os.path.basename(parsed_url.path).replace('.git', '')
repo_path = os.path.join(parent_dir, repo_name)

# Construct Git URL with credentials
git_url_with_credentials = f'https://{git_username}:{git_password}@{parsed_url.netloc}{parsed_url.path}'

# Secret token for webhook verification
SECRET_TOKEN = os.getenv('WEBHOOK_SECRET', '')  # Get from .env or leave empty


# @app.route('/webhook', methods=['POST'])
@app.route('/webhook', methods=['POST'])
def webhook():

    return jsonify({'status': 'success', 'message': 'hi'}), 200
    # Verify the token if set
    if SECRET_TOKEN:
        gitlab_token = request.headers.get('X-Gitlab-Token')
        if not gitlab_token or gitlab_token != SECRET_TOKEN:
            return jsonify({'status': 'error', 'message': 'Invalid token'}), 401
    
    # Get the event type
    event_type = request.headers.get('X-Gitlab-Event')
    
    # Process push events
    if event_type == 'Push Hook':
        try:
            # Check if repository exists locally
            if not os.path.exists(repo_path):
                print(f"Repository does not exist locally. Cloning into {repo_path}...")
                command = ['git', 'clone', git_url_with_credentials, repo_path]
                result = subprocess.run(command, check=True, capture_output=True, text=True)
                message = "Repository cloned successfully"
            else:
                print(f"Repository exists at {repo_path}. Performing git pull...")
                command = ['git', 'pull']
                result = subprocess.run(command, check=True, capture_output=True, text=True, cwd=repo_path)
                message = "Git pull executed successfully"
            
            # Log the result
            print(f"{message}: {result.stdout}")
            
            return jsonify({
                'status': 'success',
                'message': message,
                'output': result.stdout
            })
            
        except subprocess.CalledProcessError as e:
            error_message = f"Error during git operation: {e.stderr}"
            print(error_message)
            return jsonify({
                'status': 'error',
                'message': error_message
            }), 500
    
    return jsonify({'status': 'ignored', 'message': 'Event not processed'})

if __name__ == '__main__':
    # Check if credentials are available
    if not git_username or not git_password:
        print("Warning: Git credentials not found in .env file. Webhook may fail for private repositories.")
    
    # Run the Flask app
    print(f"Starting webhook server for repository: {repo_name}")
    app.run(host='0.0.0.0', port=5001)