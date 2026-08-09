import os
import base64
import requests
from mcp.server import MCPServer
mcp = MCPServer("Pterodactyl Admin Server")
# These are pulled from Render securely, so
# your keys aren't in the code!
# .rstrip("/") guards against a trailing
# slash in PANEL_URL causing double-slash
# 404s.
PANEL_URL = os.environ.get("PANEL_URL",
"").rstrip("/")
API_KEY = os.environ.get("API_KEY")
SERVER_ID = os.environ.get("SERVER_ID")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}
MODRINTH_API = "https://api.modrinth.com/v2"
# -----------------------------------------
----------------------------------
# Console
# -----------------------------------------
----------------------------------
@mcp.tool()
def run_console_command(command: str) ->
str:
    """Send a command directly to the
Minecraft server console."""
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
command"
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type":
"application/json"},
        json={"command": command},
    )
    if response.status_code == 204:
        return "Command executed
successfully."
    return f"Failed to execute command:
{response.text}"
@mcp.tool()
def power_action(action: str) -> str:
    """Control server power state. action
must be one of: start, stop, restart, kill.
    Use 'restart' after installing new
plugins for them to load. Use 'kill' only
if the
    server is unresponsive to 'stop'."""
    valid_actions = {"start", "stop",
"restart", "kill"}
    if action not in valid_actions:
        return f"Invalid action '{action}'.
Must be one of: {', '.join(valid_actions)}"
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
power"
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type":
"application/json"},
        json={"signal": action},
    )
    if response.status_code == 204:
        return f"Power action '{action}'
sent successfully."
    return f"Failed to send power action:
{response.text}"
@mcp.tool()
def get_server_status() -> str:
    """Get the server's current power state
and live resource usage
    (CPU, memory, disk, network,
uptime)."""
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
resources"
    response = requests.get(url,
headers=HEADERS)
    if response.status_code != 200:
        return f"Failed to get server
status: {response.text}"
    data =
response.json().get("attributes", {})
    state = data.get("current_state",
"unknown")
    resources = data.get("resources", {})
    memory_mb =
resources.get("memory_bytes", 0) / (1024 *
1024)
    memory_limit_mb =
resources.get("memory_limit_bytes", 0) /
(1024 * 1024)
    disk_mb = resources.get("disk_bytes",
0) / (1024 * 1024)
    cpu_percent =
resources.get("cpu_absolute", 0)
    uptime_ms = resources.get("uptime", 0)
    return (
        f"State: {state}\n"
        f"CPU: {cpu_percent:.1f}%\n"
        f"Memory: {memory_mb:.0f} MB /
{memory_limit_mb:.0f} MB\n"
        f"Disk: {disk_mb:.0f} MB\n"
        f"Uptime: {uptime_ms / 1000 /
60:.1f} minutes"
    )
# -----------------------------------------
----------------------------------
# Files - text
# -----------------------------------------
----------------------------------
@mcp.tool()
def read_server_file(file_path: str) ->
str:
    """Read a text file from the server
(e.g., /server.properties or
/logs/latest.log)."""
    if not file_path.startswith("/"):
        file_path = "/" + file_path
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
files/contents"
    response = requests.get(url,
headers=HEADERS, params={"file":
file_path})
    if response.status_code == 200:
        return response.text
    return f"Failed to read file:
{response.text}"
@mcp.tool()
def write_server_file(file_path: str,
content: str) -> str:
    """Write or overwrite a TEXT file on
the server. If the file does not exist, it
will
    be created. Do NOT use this for binary
files like .jar plugins - use
upload_binary_file
    or install_plugin_from_url instead,
since text writes will corrupt binary
data."""
    if not file_path.startswith("/"):
        file_path = "/" + file_path
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
files/write"
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type":
"text/plain"},
        params={"file": file_path},
        data=content.encode("utf-8"),
    )
    if response.status_code == 204:
        return f"Successfully wrote to
{file_path}"
    return f"Failed to write file:
{response.text}"
@mcp.tool()
def delete_server_file(file_path: str) ->
str:
    """Delete a file or folder from the
Minecraft server."""
    if not file_path.startswith("/"):
        file_path = "/" + file_path
    root_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    if not root_dir:
        root_dir = "/"
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
files/delete"
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type":
"application/json"},
        json={"root": root_dir, "files":
[file_name]},
    )
    if response.status_code == 204:
        return f"Successfully deleted
{file_path}"
    return f"Failed to delete file:
{response.text}"
@mcp.tool()
def list_directory(directory_path: str =
"/") -> str:
    """List files and folders inside a
directory on the server (e.g. '/plugins' or
'/').
    Useful for checking what plugins are
currently installed."""
    if not directory_path.startswith("/"):
        directory_path = "/" +
directory_path
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
files/list"
    response = requests.get(url,
headers=HEADERS, params={"directory":
directory_path})
    if response.status_code != 200:
        return f"Failed to list directory:
{response.text}"
    entries = response.json().get("data",
[])
    if not entries:
        return f"{directory_path} is
empty."
    lines = []
    for entry in entries:
        attrs = entry.get("attributes", {})
        name = attrs.get("name", "?")
        is_dir = attrs.get("is_file") is
False
        size = attrs.get("size", 0)
        marker = "[DIR] " if is_dir else
"      "
        size_str = "" if is_dir else f"
({size} bytes)"
        lines.append(f"{marker}{name}
{size_str}")
    return f"Contents of
{directory_path}:\n" + "\n".join(lines)
# -----------------------------------------
----------------------------------
# Files - binary (plugins, etc)
# -----------------------------------------
----------------------------------
@mcp.tool()
def upload_binary_file(file_path: str,
base64_content: str) -> str:
    """Upload a binary file (like a .jar
plugin) to the server, given base64-encoded
content.
    Use this instead of write_server_file
for any non-text file (jars, zips, images,
etc)."""
    if not file_path.startswith("/"):
        file_path = "/" + file_path
    try:
        raw_bytes =
base64.b64decode(base64_content)
    except Exception as e:
        return f"Failed to decode base64
content: {e}"
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
files/write"
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type":
"application/octet-stream"},
        params={"file": file_path},
        data=raw_bytes,
    )
    if response.status_code == 204:
        return f"Successfully uploaded
{file_path} ({len(raw_bytes)} bytes)"
    return f"Failed to upload file:
{response.text}"
@mcp.tool()
def install_plugin_from_url(download_url:
str, plugin_filename: str) -> str:
    """Download a plugin jar from a direct
URL (e.g. a Modrinth CDN download link)
    and install it into the server's
/plugins folder."""
    if not
plugin_filename.endswith(".jar"):
        plugin_filename += ".jar"
    try:
        dl_response =
requests.get(download_url, timeout=60)
        dl_response.raise_for_status()
    except Exception as e:
        return f"Failed to download plugin
from URL: {e}"
    file_path =
f"/plugins/{plugin_filename}"
    url = f"
{PANEL_URL}/api/client/servers/{SERVER_ID}/
files/write"
    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type":
"application/octet-stream"},
        params={"file": file_path},
        data=dl_response.content,
    )
    if response.status_code == 204:
        return f"Successfully installed
{plugin_filename}
({len(dl_response.content)} bytes) to
/plugins. Restart the server for it to
load."
    return f"Failed to write plugin file:
{response.text}"
# -----------------------------------------
----------------------------------
# Modrinth plugin search
# -----------------------------------------
----------------------------------
@mcp.tool()
def search_modrinth_plugins(query: str,
limit: int = 5) -> str:
    """Search Modrinth for Minecraft
plugins/mods matching a query.
    Returns project slugs, titles, and
descriptions. Use get_modrinth_download_url
    afterward with a chosen slug to get the
actual installable file."""
    response = requests.get(
        f"{MODRINTH_API}/search",
        params={
            "query": query,
            "limit": limit,
            "facets":
'[["project_type:plugin"]]',
        },
    )
    if response.status_code != 200:
        return f"Failed to search Modrinth:
{response.text}"
    hits = response.json().get("hits", [])
    if not hits:
        return f"No plugins found matching
'{query}'."
    lines = []
    for hit in hits:
        slug = hit.get("slug", "?")
        title = hit.get("title", "?")
        description =
hit.get("description", "")
        downloads = hit.get("downloads", 0)
        lines.append(f"- {title} (slug:
{slug}) — {downloads:,} downloads\n 
{description}")
    return f"Modrinth results for
'{query}':\n" + "\n".join(lines)
@mcp.tool()
def get_modrinth_download_url(project_slug:
str, game_version: str = "", loader: str =
"paper") -> str:
    """Get the direct download URL and
filename for the latest matching version of
a
    Modrinth project. Optionally filter by
game_version (e.g. '1.21.4') and loader
    (e.g. 'paper', 'spigot', 'bukkit').
Pass the result's URL and filename to
    install_plugin_from_url to actually
install it."""
    params = {}
    if loader:
        params["loaders"] = f'["{loader}"]'
    if game_version:
        params["game_versions"] = f'["
{game_version}"]'
    response = requests.get(
        f"
{MODRINTH_API}/project/{project_slug}/versi
on",
        params=params,
    )
    if response.status_code != 200:
        return f"Failed to fetch versions
for '{project_slug}': {response.text}"
    versions = response.json()
    if not versions:
        return f"No matching versions found
for '{project_slug}' with loader={loader}
game_version={game_version or 'any'}."
    latest = versions[0]
    files = latest.get("files", [])
    if not files:
        return f"Version found but no
downloadable files listed for
'{project_slug}'."
    primary_file = next((f for f in files
if f.get("primary")), files[0])
    return (
        f"Filename:
{primary_file.get('filename')}\n"
        f"Download URL:
{primary_file.get('url')}\n"
        f"Version:
{latest.get('version_number')}\n"
        f"Game versions: {',
'.join(latest.get('game_versions', []))}"
    )
# -----------------------------------------
----------------------------------
# Entry point
# -----------------------------------------
----------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT",
3001))
    print(f"Starting MCP server on 0.0.0.0:
{port}...")
    print(f"Panel URL configured:
{bool(PANEL_URL)}")
    print(f"API key configured:
{bool(API_KEY)}")
    print(f"Server ID configured:
{bool(SERVER_ID)}")
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )
