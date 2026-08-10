import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from mcp.server import MCPServer

mcp = MCPServer("Pterodactyl Admin Server")

# These are pulled from Render securely, so your keys aren't in the code!
# .rstrip("/") guards against a trailing slash in PANEL_URL causing double-slash 404s.
PANEL_URL = os.environ.get("PANEL_URL", "").rstrip("/")
API_KEY = os.environ.get("API_KEY")
SERVER_ID = os.environ.get("SERVER_ID")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

MODRINTH_API = "https://api.modrinth.com/v2"


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

@mcp.tool()
def run_console_command(command: str) -> str:
    """Send a command directly to the Minecraft server console."""

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/command"

    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"command": command},
    )

    if response.status_code == 204:
        return "Command executed successfully."
    return f"Failed to execute command: {response.text}"


@mcp.tool()
def power_action(action: str) -> str:
    """Control server power state. action must be one of: start, stop, restart, kill.
    Use 'restart' after installing new plugins for them to load. Use 'kill' only if the
    server is unresponsive to 'stop'."""

    valid_actions = {"start", "stop", "restart", "kill"}
    if action not in valid_actions:
        return f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}"

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/power"

    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"signal": action},
    )

    if response.status_code == 204:
        return f"Power action '{action}' sent successfully."
    return f"Failed to send power action: {response.text}"


@mcp.tool()
def get_server_status() -> str:
    """Get the server's current power state and live resource usage
    (CPU, memory, disk, network, uptime)."""

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/resources"

    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        return f"Failed to get server status: {response.text}"

    data = response.json().get("attributes", {})
    state = data.get("current_state", "unknown")
    resources = data.get("resources", {})

    memory_mb = resources.get("memory_bytes", 0) / (1024 * 1024)
    memory_limit_mb = resources.get("memory_limit_bytes", 0) / (1024 * 1024)
    disk_mb = resources.get("disk_bytes", 0) / (1024 * 1024)
    cpu_percent = resources.get("cpu_absolute", 0)
    uptime_ms = resources.get("uptime", 0)

    return (
        f"State: {state}\n"
        f"CPU: {cpu_percent:.1f}%\n"
        f"Memory: {memory_mb:.0f} MB / {memory_limit_mb:.0f} MB\n"
        f"Disk: {disk_mb:.0f} MB\n"
        f"Uptime: {uptime_ms / 1000 / 60:.1f} minutes"
    )


# ---------------------------------------------------------------------------
# Files - text
# ---------------------------------------------------------------------------

def _collapse_repeated_lines(text: str) -> str:
    """Collapse runs of identical consecutive lines into a single line + count.
    Minecraft logs especially tend to spam the same warning/error repeatedly,
    which burns tokens for no extra information."""

    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and lines[j] == lines[i]:
            j += 1
        run_len = j - i
        if run_len >= 3:
            out.append(f"{lines[i]}  [x{run_len} repeated]")
        else:
            out.extend(lines[i:j])
        i = j
    return "\n".join(out)


def _fetch_and_truncate_file(file_path: str, lines: int = 0, max_chars: int = 20000) -> str:
    """Shared logic: fetch a single file's contents, collapse repeated lines, and
    truncate per lines/max_chars rules to keep output compact."""

    if not file_path.startswith("/"):
        file_path = "/" + file_path

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/contents"

    try:
        response = requests.get(url, headers=HEADERS, params={"file": file_path}, timeout=30)
    except Exception as e:
        return f"Failed to read file: {e}"

    if response.status_code != 200:
        return f"Failed to read file: {response.text}"

    content = response.text
    original_len = len(content)

    if lines > 0:
        split_lines = content.splitlines()
        truncated = len(split_lines) > lines
        selected = split_lines[-lines:]
        result = _collapse_repeated_lines("\n".join(selected))
        if truncated:
            result = f"...[{len(split_lines) - lines} earlier lines omitted]...\n" + result
        return result

    if max_chars and original_len > max_chars:
        tail = content[-max_chars:]
        tail = _collapse_repeated_lines(tail)
        return f"...[{original_len - max_chars} earlier chars omitted]...\n{tail}"

    return _collapse_repeated_lines(content)


@mcp.tool()
def read_server_file(file_path: str, lines: int = 0, max_chars: int = 20000) -> str:
    """Read a text file from the server (e.g., /server.properties or /logs/latest.log).

    Token-efficient by default: returns only the END of the file capped at max_chars
    characters (default 20000, tune lower/higher as needed), and collapses runs of
    3+ identical consecutive lines (common in spammy logs) into one line + a count.
    Pass lines > 0 to instead return just the last N lines. Pass max_chars=0 for the
    full file (use sparingly - can consume a lot of tokens).
    """
    return _fetch_and_truncate_file(file_path, lines=lines, max_chars=max_chars)


@mcp.tool()
def read_server_files(file_paths: list[str], lines: int = 0, total_char_budget: int = 8000) -> str:
    """Read multiple text files from the server concurrently and token-efficiently.

    Files are fetched in parallel (not sequentially), so many files can be read without
    bottlenecking on slow requests. To keep total output small regardless of how many
    files are requested, total_char_budget (default 8000) is split evenly across all
    files unless lines > 0 is given, in which case each file returns its last N lines
    instead. Repeated consecutive log lines are collapsed into one line + a count.

    Returns results concatenated together, each labeled with its file path.
    """

    if not file_paths:
        return "No file paths provided."

    per_file_chars = 0 if lines > 0 else max(500, total_char_budget // len(file_paths))

    results: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=min(len(file_paths), 8)) as executor:
        future_to_path = {
            executor.submit(_fetch_and_truncate_file, path, lines, per_file_chars): path
            for path in file_paths
        }
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                results[path] = future.result()
            except Exception as e:
                results[path] = f"Failed to read file: {e}"

    sections = []
    for path in file_paths:
        normalized = path if path.startswith("/") else "/" + path
        sections.append(f"===== {normalized} =====\n{results.get(path, 'No result')}")

    return "\n\n".join(sections)


@mcp.tool()
def write_server_file(file_path: str, content: str) -> str:
    """Write or overwrite a TEXT file on the server. If the file does not exist, it will
    be created. Do NOT use this for binary files like .jar plugins - use pull_file_from_url
    or install_plugin_from_url instead, since text writes will corrupt binary data."""

    if not file_path.startswith("/"):
        file_path = "/" + file_path

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/write"

    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "text/plain"},
        params={"file": file_path},
        data=content.encode("utf-8"),
    )

    if response.status_code == 204:
        return f"Successfully wrote to {file_path}"
    return f"Failed to write file: {response.text}"


@mcp.tool()
def delete_server_file(file_path: str) -> str:
    """Delete a file or folder from the Minecraft server."""

    if not file_path.startswith("/"):
        file_path = "/" + file_path

    root_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    if not root_dir:
        root_dir = "/"

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/delete"

    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"root": root_dir, "files": [file_name]},
    )

    if response.status_code == 204:
        return f"Successfully deleted {file_path}"
    return f"Failed to delete file: {response.text}"


@mcp.tool()
def move_server_file(file_path: str, destination_path: str) -> str:
    """Move or rename a file/folder on the server. Provide the full current path and the
    full new path (e.g. move_server_file('/world/old.log', '/backups/old.log') or rename
    in place with move_server_file('/plugins/foo.jar', '/plugins/foo.jar.disabled'))."""

    if not file_path.startswith("/"):
        file_path = "/" + file_path
    if not destination_path.startswith("/"):
        destination_path = "/" + destination_path

    root_dir = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)
    if not root_dir:
        root_dir = "/"

    # Pterodactyl's rename "to" is relative to root, so strip the shared root prefix
    dest_to = destination_path
    if root_dir != "/" and destination_path.startswith(root_dir + "/"):
        dest_to = destination_path[len(root_dir) + 1:]
    elif root_dir == "/" and destination_path.startswith("/"):
        dest_to = destination_path[1:]

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/rename"

    response = requests.put(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"root": root_dir, "files": [{"from": file_name, "to": dest_to}]},
    )

    if response.status_code == 204:
        return f"Successfully moved {file_path} -> {destination_path}"
    return f"Failed to move file: {response.text}"


@mcp.tool()
def get_file_download_url(file_path: str) -> str:
    """Get a temporary signed download URL for a file on the server, so it can be
    downloaded directly (e.g. to hand to a user, or to feed into another tool)."""

    if not file_path.startswith("/"):
        file_path = "/" + file_path

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/download"

    response = requests.get(url, headers=HEADERS, params={"file": file_path})

    if response.status_code != 200:
        return f"Failed to get download URL: {response.text}"

    signed_url = response.json().get("attributes", {}).get("url", "")
    if not signed_url:
        return "Failed to get download URL: no URL returned."
    return f"Download URL for {file_path} (temporary, expires shortly):\n{signed_url}"



    """List files and folders inside a directory on the server (e.g. '/plugins' or '/').
    Useful for checking what plugins are currently installed."""

    if not directory_path.startswith("/"):
        directory_path = "/" + directory_path

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/list"

    response = requests.get(url, headers=HEADERS, params={"directory": directory_path})

    if response.status_code != 200:
        return f"Failed to list directory: {response.text}"

    entries = response.json().get("data", [])
    if not entries:
        return f"{directory_path} is empty."

    lines = []
    for entry in entries:
        attrs = entry.get("attributes", {})
        name = attrs.get("name", "?")
        is_dir = attrs.get("is_file") is False
        size = attrs.get("size", 0)
        marker = "[DIR] " if is_dir else "      "
        size_str = "" if is_dir else f" ({size} bytes)"
        lines.append(f"{marker}{name}{size_str}")

    return f"Contents of {directory_path}:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Files - binary (plugins, etc)
# ---------------------------------------------------------------------------
# Note: no base64-upload tool here on purpose - passing binary file content through
# the model as base64 text burns huge amounts of tokens. Use pull_file_from_url or
# install_plugin_from_url instead, which download server-side from a URL and never
# put the file bytes in the conversation.

@mcp.tool()
def pull_file_from_url(download_url: str, destination_path: str) -> str:
    """Download a file from any direct URL and write it to any path on the server.
    Generic version of install_plugin_from_url - not limited to /plugins or .jar files.
    Use this for datapacks, worlds, resource packs, configs, etc. The file is streamed
    through this server and written via the panel's binary write endpoint."""

    if not destination_path.startswith("/"):
        destination_path = "/" + destination_path

    try:
        dl_response = requests.get(download_url, timeout=120)
        dl_response.raise_for_status()
    except Exception as e:
        return f"Failed to download from URL: {e}"

    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/write"

    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/octet-stream"},
        params={"file": destination_path},
        data=dl_response.content,
    )

    if response.status_code == 204:
        return f"Successfully pulled {destination_path} ({len(dl_response.content)} bytes)"
    return f"Failed to write pulled file: {response.text}"


@mcp.tool()
def install_plugin_from_url(download_url: str, plugin_filename: str) -> str:
    """Download a plugin jar from a direct URL (e.g. a Modrinth CDN download link)
    and install it into the server's /plugins folder."""

    if not plugin_filename.endswith(".jar"):
        plugin_filename += ".jar"

    try:
        dl_response = requests.get(download_url, timeout=60)
        dl_response.raise_for_status()
    except Exception as e:
        return f"Failed to download plugin from URL: {e}"

    file_path = f"/plugins/{plugin_filename}"
    url = f"{PANEL_URL}/api/client/servers/{SERVER_ID}/files/write"

    response = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/octet-stream"},
        params={"file": file_path},
        data=dl_response.content,
    )

    if response.status_code == 204:
        return f"Successfully installed {plugin_filename} ({len(dl_response.content)} bytes) to /plugins. Restart the server for it to load."
    return f"Failed to write plugin file: {response.text}"


# ---------------------------------------------------------------------------
# Modrinth plugin search
# ---------------------------------------------------------------------------

@mcp.tool()
def search_modrinth_plugins(query: str, limit: int = 5) -> str:
    """Search Modrinth for Minecraft plugins/mods matching a query.
    Returns project slugs, titles, and descriptions. Use get_modrinth_download_url
    afterward with a chosen slug to get the actual installable file."""

    response = requests.get(
        f"{MODRINTH_API}/search",
        params={
            "query": query,
            "limit": limit,
            "facets": '[["project_type:plugin"]]',
        },
    )

    if response.status_code != 200:
        return f"Failed to search Modrinth: {response.text}"

    hits = response.json().get("hits", [])
    if not hits:
        return f"No plugins found matching '{query}'."

    lines = []
    for hit in hits:
        slug = hit.get("slug", "?")
        title = hit.get("title", "?")
        description = hit.get("description", "")
        downloads = hit.get("downloads", 0)
        lines.append(f"- {title} (slug: {slug}) — {downloads:,} downloads\n  {description}")

    return f"Modrinth results for '{query}':\n" + "\n".join(lines)


@mcp.tool()
def get_modrinth_download_url(project_slug: str, game_version: str = "", loader: str = "paper") -> str:
    """Get the direct download URL and filename for the latest matching version of a
    Modrinth project. Optionally filter by game_version (e.g. '1.21.4') and loader
    (e.g. 'paper', 'spigot', 'bukkit'). Pass the result's URL and filename to
    install_plugin_from_url to actually install it."""

    params = {}
    if loader:
        params["loaders"] = f'["{loader}"]'
    if game_version:
        params["game_versions"] = f'["{game_version}"]'

    response = requests.get(
        f"{MODRINTH_API}/project/{project_slug}/version",
        params=params,
    )

    if response.status_code != 200:
        return f"Failed to fetch versions for '{project_slug}': {response.text}"

    versions = response.json()
    if not versions:
        return f"No matching versions found for '{project_slug}' with loader={loader} game_version={game_version or 'any'}."

    latest = versions[0]
    files = latest.get("files", [])
    if not files:
        return f"Version found but no downloadable files listed for '{project_slug}'."

    primary_file = next((f for f in files if f.get("primary")), files[0])

    return (
        f"Filename: {primary_file.get('filename')}\n"
        f"Download URL: {primary_file.get('url')}\n"
        f"Version: {latest.get('version_number')}\n"
        f"Game versions: {', '.join(latest.get('game_versions', []))}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3001))

    print(f"Starting MCP server on 0.0.0.0:{port}...")
    print(f"Panel URL configured: {bool(PANEL_URL)}")
    print(f"API key configured: {bool(API_KEY)}")
    print(f"Server ID configured: {bool(SERVER_ID)}")

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
    )
