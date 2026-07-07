# backend/mcp/manager.py
import subprocess, json, asyncio, os, shutil, sys
from pathlib import Path
from db import get_session
from db.models import MCPServer
from .client import MCPClient

MCP_REGISTRY = {
    'filesystem': {
        'display_name': 'Filesystem',
        'description': 'Read and write local files',
        'category': 'filesystem',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-filesystem', '{WORKSPACE_PATH}'],
        'required_env_keys': [],
    },
    'github': {
        'display_name': 'GitHub',
        'description': 'Search repos, PRs, issues via GitHub API',
        'category': 'git',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-github'],
        'required_env_keys': ['GITHUB_TOKEN'],
    },
    'brave-search': {
        'display_name': 'Brave Search',
        'description': 'Web search via Brave',
        'category': 'web',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-brave-search'],
        'required_env_keys': ['BRAVE_API_KEY'],
    },
    'memory': {
        'display_name': 'Memory',
        'description': 'Persistent AI memory across sessions',
        'category': 'memory',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-memory'],
        'required_env_keys': [],
    },
    'puppeteer': {
        'display_name': 'Puppeteer (Browser)',
        'description': 'Control a browser, scrape web pages',
        'category': 'web',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-puppeteer'],
        'required_env_keys': [],
    },
    'git': {
        'display_name': 'Git',
        'description': 'Git operations on local repos',
        'category': 'git',
        'command': 'uvx',
        'args': ['mcp-server-git', '--repository', '{WORKSPACE_PATH}'],
        'required_env_keys': [],
    },
    'postgres': {
        'display_name': 'PostgreSQL',
        'description': 'Query PostgreSQL databases',
        'category': 'database',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-postgres', '{DATABASE_URL}'],
        'required_env_keys': ['DATABASE_URL'],
    },
    'slack': {
        'display_name': 'Slack',
        'description': 'Read Slack channels and messages',
        'category': 'communication',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-slack'],
        'required_env_keys': ['SLACK_BOT_TOKEN'],
    },
    'gitlab': {
        'display_name': 'GitLab',
        'description': 'GitLab projects, MRs, issues',
        'category': 'git',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-gitlab'],
        'required_env_keys': ['GITLAB_PERSONAL_ACCESS_TOKEN'],
    },
    'google-maps': {
        'display_name': 'Google Maps',
        'description': 'Location search and directions',
        'category': 'web',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-google-maps'],
        'required_env_keys': ['GOOGLE_MAPS_API_KEY'],
    },
}


class MCPManager:
    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}
        self._clients: dict[str, MCPClient] = {}

    async def install(self, mcp_id: str, config: dict) -> dict:
        if mcp_id not in MCP_REGISTRY:
            return {'status': 'error', 'error': f'Unknown MCP: {mcp_id}'}

        spec = MCP_REGISTRY[mcp_id]

        # Validate required config keys
        for key in spec['required_env_keys']:
            if key not in config:
                return {'status': 'error', 'error': f'Missing required config: {key}'}

        # Substitute variables into args
        try:
            args = [a.format(**config) for a in spec['args']]
        except KeyError as exc:
            return {'status': 'error', 'error': f'Missing required config: {exc.args[0]}'}

        # Write config to .forge/mcp.json in workspace
        workspace = config.get('WORKSPACE_PATH', '.')
        config_path = Path(workspace) / '.forge' / 'mcp.json'
        config_path.parent.mkdir(exist_ok=True)

        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except Exception:
                pass

        existing[mcp_id] = {
            'command': spec['command'],
            'args': args,
            'env': {k: config[k] for k in spec['required_env_keys'] if k in config},
        }
        config_path.write_text(json.dumps(existing, indent=2))

        # Spawn the MCP server process
        env_overrides = {k: config[k] for k in spec['required_env_keys'] if k in config}
        spawn_result = await self._spawn(mcp_id, spec['command'], args, env_overrides)
        if spawn_result['status'] != 'ready':
            return spawn_result

        # Update database
        with get_session() as db:
            db.merge(MCPServer(
                id=mcp_id,
                display_name=spec['display_name'],
                description=spec['description'],
                category=spec['category'],
                is_installed=True,
                is_running=True,
            ))
            db.commit()

        return {'status': 'ready'}

    @staticmethod
    def _missing_command_error(command: str) -> str:
        if command == 'uvx':
            return "uvx not found. Install uv first (pip install uv, or winget install astral-sh.uv), then retry."
        return f'{command} not found. Install Node.js and npm, then retry.'

    @staticmethod
    def _resolve_command(command: str) -> str | None:
        found = shutil.which(command)
        if found:
            return found
        # pip-installed launchers (e.g. uvx) often live in Python Scripts
        # dirs that Windows doesn't put on PATH
        import sysconfig
        scheme = 'nt_user' if os.name == 'nt' else 'posix_user'
        for path in {sysconfig.get_path('scripts'), sysconfig.get_path('scripts', scheme)}:
            if path:
                found = shutil.which(command, path=path)
                if found:
                    return found
        return None

    async def _spawn(self, mcp_id: str, command: str, args: list, env_overrides: dict) -> dict:
        """Shared spawn logic used by install(), relaunch_installed(), and start().

        Resolves `command` on PATH, launches it with `args`/`env_overrides`,
        records the process in self._processes, and performs the ~1s
        aliveness health check. Does NOT touch the database — callers own
        that. Returns {'status': 'ready'} or {'status': 'error', 'error': ...}.
        """
        executable = self._resolve_command(command)
        if executable is None:
            return {'status': 'error', 'error': self._missing_command_error(command)}

        env = {**os.environ, **env_overrides}
        try:
            proc = subprocess.Popen(
                [executable] + args,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:
            return {'status': 'error', 'error': str(exc)}

        self._processes[mcp_id] = proc

        # Health check: wait 1s, verify process is alive
        await asyncio.sleep(1.0)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode(errors='ignore')
            return {'status': 'error', 'error': stderr or 'Process exited immediately'}

        # Wire up the MCP JSON-RPC client (stdio) so the router can call this
        # server's tools. Best-effort: an init failure must not fail the spawn
        # itself -- the process keeps running, it just contributes no tools.
        try:
            client = MCPClient(proc)
            await asyncio.to_thread(client.initialize)
            await asyncio.to_thread(client.list_tools)  # warm the cache
            self._clients[mcp_id] = client
        except Exception as exc:
            print(f'[mcp] {mcp_id}: MCP client init failed, no tools will be available: {exc}', file=sys.stderr)

        return {'status': 'ready'}

    async def uninstall(self, mcp_id: str):
        if mcp_id in self._processes:
            self._processes[mcp_id].terminate()
            del self._processes[mcp_id]
        self._clients.pop(mcp_id, None)
        with get_session() as db:
            server = db.query(MCPServer).filter_by(id=mcp_id).first()
            if server:
                server.is_installed = False
                server.is_running = False
                db.commit()

    def list_all(self) -> list:
        result = []
        for mcp_id, spec in MCP_REGISTRY.items():
            proc = self._processes.get(mcp_id)
            is_running = proc is not None and proc.poll() is None
            result.append({
                'id': mcp_id,
                'display_name': spec['display_name'],
                'description': spec['description'],
                'category': spec['category'],
                'required_keys': spec['required_env_keys'],
                'status': 'running' if is_running else ('installed' if self._is_installed(mcp_id) else 'not_installed'),
            })
        return result

    def _is_installed(self, mcp_id: str) -> bool:
        with get_session() as db:
            s = db.query(MCPServer).filter_by(id=mcp_id).first()
            return s is not None and s.is_installed

    async def stop_all(self):
        for proc in self._processes.values():
            try:
                proc.terminate()
            except Exception:
                pass
        self._clients.clear()

    def get_all_tools(self) -> list:
        """Aggregated list of tools across all currently-running MCP servers
        that have an initialized client, in the shape the router expects:
        [{'server', 'name', 'description', 'input_schema'}, ...].
        Reads from each client's cached tools/list result -- no I/O here.
        """
        tools = []
        for mcp_id, client in list(self._clients.items()):
            proc = self._processes.get(mcp_id)
            if proc is None or proc.poll() is not None:
                # Process died without going through uninstall() - drop it.
                self._clients.pop(mcp_id, None)
                continue
            try:
                server_tools = client.list_tools()  # cached after warm-up in _spawn
            except Exception:
                continue
            for t in server_tools:
                tools.append({
                    'server': mcp_id,
                    'name': t.get('name'),
                    'description': t.get('description', ''),
                    'input_schema': t.get('inputSchema') or {'type': 'object', 'properties': {}},
                })
        return tools

    async def call_tool(self, server: str, name: str, arguments: dict):
        client = self._clients.get(server)
        proc = self._processes.get(server)
        if client is None or proc is None or proc.poll() is not None:
            raise RuntimeError(f'MCP server "{server}" is not running or has no initialized tool client')
        return await asyncio.to_thread(client.call_tool, name, arguments)

    async def relaunch_installed(self, workspace_path: str) -> dict:
        """Re-spawn MCP servers that were installed (is_installed=True in db) but
        are not currently running (e.g. after a backend restart). Reads the
        previously-persisted command/args/env from <workspace>/.forge/mcp.json.
        """
        relaunched: list[str] = []
        failed: dict[str, str] = {}

        config_path = Path(workspace_path) / '.forge' / 'mcp.json'
        try:
            entries: dict = json.loads(config_path.read_text())
        except Exception:
            entries = {}

        for mcp_id, entry in entries.items():
            proc = self._processes.get(mcp_id)
            if proc is not None and proc.poll() is None:
                continue  # already running

            with get_session() as db:
                server = db.query(MCPServer).filter_by(id=mcp_id).first()
                installed = server is not None and server.is_installed

            if not installed:
                continue

            command = entry.get('command')
            args = entry.get('args', [])
            env_overrides = entry.get('env', {})

            if not command:
                failed[mcp_id] = 'Missing command in .forge/mcp.json'
                continue

            spawn_result = await self._spawn(mcp_id, command, args, env_overrides)
            if spawn_result['status'] != 'ready':
                failed[mcp_id] = spawn_result['error']
                continue

            with get_session() as db:
                server = db.query(MCPServer).filter_by(id=mcp_id).first()
                if server:
                    server.is_running = True
                    db.commit()

            relaunched.append(mcp_id)

        return {'relaunched': relaunched, 'failed': failed}

    async def start(self, mcp_id: str, workspace_path: str) -> dict:
        """Re-spawn a single MCP server that is installed but not currently
        running (e.g. the user stopped it, or it died after a backend
        restart before relaunch_installed() got to it). Reads the
        previously-persisted command/args/env from
        <workspace>/.forge/mcp.json, the same source relaunch_installed()
        uses.
        """
        proc = self._processes.get(mcp_id)
        if proc is not None and proc.poll() is None:
            return {'status': 'ready'}  # already running

        with get_session() as db:
            server = db.query(MCPServer).filter_by(id=mcp_id).first()
            installed = server is not None and server.is_installed

        if not installed:
            return {'status': 'error', 'error': f'{mcp_id} is not installed'}

        config_path = Path(workspace_path) / '.forge' / 'mcp.json'
        try:
            entries: dict = json.loads(config_path.read_text())
        except Exception:
            entries = {}

        entry = entries.get(mcp_id)
        if not entry:
            return {'status': 'error', 'error': f'No saved configuration found for {mcp_id} in .forge/mcp.json'}

        command = entry.get('command')
        args = entry.get('args', [])
        env_overrides = entry.get('env', {})

        if not command:
            return {'status': 'error', 'error': 'Missing command in .forge/mcp.json'}

        spawn_result = await self._spawn(mcp_id, command, args, env_overrides)
        if spawn_result['status'] != 'ready':
            return spawn_result

        with get_session() as db:
            server = db.query(MCPServer).filter_by(id=mcp_id).first()
            if server:
                server.is_running = True
                db.commit()

        return {'status': 'ready'}
