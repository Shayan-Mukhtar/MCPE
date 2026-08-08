import os
import requests
from mcp.server import MCPServer

mcp = MCPServer("Pterodactyl Admin Server")

These pull from Render securely, so your keys aren't in the code!
PANEL_URL = os.environ.get("PANEL_URL")
API_KEY = os.environ.get("API_KEY")
SERVER_ID = os.environ.get("SERVER_ID")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

@mcp.tool()
def run_console_command(command: str) -> str:
    """Send a command directly to the Minecraft server console."""
    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/command"
    response = requests.post(
        url, 
        headers={HEADERS, "Content-Type": "application/json"}, 
        json={"command": command}
    )
    if response.status_code == 204:
        return "Command executed successfully."
    else:
        return f"Failed to execute command: {response.text}"

@mcp.tool()
def read_server_file(file_path: str) -> str:
    """Read a file from the server (e.g., /server.properties or /logs/latest.log)."""
    if not file_path.startswith("/"): 
        file_path = "/" + file_path

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/contents"
    response = requests.get(url, headers=HEADERS, params={"file": file_path})

    if response.status_code == 200:
        return response.text
    else:
        return f"Failed to read file: {response.text}"

@mcp.tool()
def write_server_file(file_path: str, content: str) -> str:
    """Write or overwrite a file on the server. If the file does not exist, it will be created."""
    if not file_path.startswith("/"): 
        file_path = "/" + file_path

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/write"
    write_headers = {HEADERS, "Content-Type": "text/plain"}

    response = requests.post(
        url, 
        headers=write_headers, 
        params={"file":
file_path}, 
        data=content.encode('utf-8')
    )
    if response.status_code == 204:
        return f"Successfully wrote to {file_path}"
    else:
        return f"Failed to write file: {response.text}"

@mcp.tool()
def delete_server_file(file_path: str) -> str:
    """Delete a file or folder from the Minecraft server."""
    if not file_path.startswith("/"): 
        file_path = "/" + file_path

Pterodactyl's delete API requires separating the folder path and the file name
    root_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)

    if not root_dir: 
        root_dir = "/"

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/delete"
    payload = {
        "root": root_dir,
        "files": [file_name]
    }

    response = requests.post(
        url, 
        headers={**HEADERS, "Content-Type": "application/json"}, 
        json=payload
    )
    if response.status_code == 204:
        return f"Successfully deleted {file_path}"
    else:
        return f"Failed to delete file: {response.text}"

if name == "main":
    # Render assigns a dynamic port automatically, defaulting to 3001 if none is found
    port = int(os.environ.get("PORT", 3001))
    mcp.run(transport="streamable-http", port=port)
