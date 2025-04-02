import os
import subprocess
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables from a .env file
load_dotenv()

# Retrieve Git credentials from the environment
git_username = os.getenv('GIT_USERNAME')
git_password = os.getenv('GIT_PASSWORD')

# Check if the credentials are available
if not git_username or not git_password:
    raise ValueError("Git credentials (GIT_USERNAME and GIT_PASSWORD) are required in the .env file.")

# Define the HTTPS repository URL (clone command URL)
repo_url = 'https://mygit.th-deg.de/ai-project-summer-25/llmano-2.git'

# Parse the URL to ensure it's in the correct format
parsed_url = urlparse(repo_url)
if not parsed_url.scheme or not parsed_url.netloc:
    raise ValueError("The provided repository URL is invalid.")

# Get the directory where this Python script is located
script_dir = os.path.dirname(os.path.realpath(__file__))

# Get the parent directory of the script (two levels up)
parent_dir = os.path.dirname(script_dir)

# Construct the Git URL with embedded credentials
git_url_with_credentials = f'https://{git_username}:{git_password}@{parsed_url.netloc}{parsed_url.path}'

# Extract the repository name from the URL (removing '.git' extension)
repo_name = os.path.basename(parsed_url.path).replace('.git', '')

# Define the target directory to clone the repository in the parent directory
clone_dir = os.path.join(parent_dir, repo_name)

# Run the Git clone command in the desired directory
try:
    if not os.path.exists(clone_dir):
        print(f"Cloning repository into {clone_dir}...")
        command = ['git', 'clone', git_url_with_credentials, clone_dir]
        subprocess.run(command, check=True)
        print("Git clone successful!")
    else:
        print(f"Directory {clone_dir} already exists. Performing git pull instead...")
        # If the directory exists, run git pull to update it
        command = ['git', 'pull', git_url_with_credentials]
        subprocess.run(command, check=True, cwd=clone_dir)
        print("Git pull successful!")
except subprocess.CalledProcessError as e:
    print(f"Error during git operation: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
