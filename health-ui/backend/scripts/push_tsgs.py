import os
import frontmatter

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from pathlib import Path

# 1. Get the directory where the current file is located
current_dir = Path(__file__).resolve().parent

# 2. Go up levels to find the root .env (adjust the .parent calls as needed)
# Based on your path: backend/app/ -> backend/ -> root/
root_env = current_dir.parent.parent / ".env"

# 3. Load specifically from that path
load_dotenv(dotenv_path=root_env)

# --- Configuration ---
ACCOUNT_URL = os.getenv("STORAGE_ACCOUNT_URL") or ""
CONTAINER_NAME = "tsgs-container"
LOCAL_FOLDER =  os.path.join(current_dir.parent, "tsgs")  # Adjust path as needed
# CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING") or ""

def upload_tsgs():
    # Initialize the Blob Service Client
    credential = DefaultAzureCredential()
    blob_service_client = BlobServiceClient(account_url=ACCOUNT_URL, credential=credential)

    # blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)

    # Ensure container exists
    if not container_client.exists():
        container_client.create_container()

    # Loop through the files in your local tsgs folder
    for filename in os.listdir(LOCAL_FOLDER):
        if filename.endswith(".md"):
            file_path = os.path.join(LOCAL_FOLDER, filename)
            
            # 1. Parse YAML using python-frontmatter
            with open(file_path, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            
            # 2. Extract specific metadata fields
            # We use .get() to avoid errors if a field is missing in the YAML
            blob_metadata = {
                "issue_type": str(post.get("issue_type", "unknown")),
                "component": str(post.get("component", "unknown")),
                "phase": str(post.get("phase", "unknown")),
                "severity": str(post.get("severity", "normal"))
            }

            # 3. Upload to Blob Storage with Metadata
            blob_client = container_client.get_blob_client(filename)
            print(f"Uploading {filename} with metadata: {blob_metadata}...")
            
            with open(file_path, "rb") as data:
                blob_client.upload_blob(
                    data, 
                    overwrite=True, 
                    metadata=blob_metadata
                )

    print("\n✅ All TSG files pushed successfully.")

if __name__ == "__main__":
    upload_tsgs()