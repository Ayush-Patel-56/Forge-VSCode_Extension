# backend/mcp/manager.py
import subprocess, json, asyncio, os, shutil
from pathlib import Path
from db import get_session
from db.models import MCPServer

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
        env = {**os.environ, **{k: config[k] for k in spec['required_env_keys'] if k in config}}
        executable = shutil.which(spec['command'])
        if executable is None:
            return {'status': 'error', 'error': self._missing_command_error(spec['command'])}
        try:
            proc = subprocess.Popen(
                [executable] + args,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return {'status': 'error', 'error': self._missing_command_error(spec['command'])}

        self._processes[mcp_id] = proc

        # Health check: wait 1s, verify process is alive
        await asyncio.sleep(1.0)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode(errors='ignore')
            return {'status': 'error', 'error': stderr or 'Process exited immediately'}

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

    async def uninstall(self, mcp_id: str):
        if mcp_id in self._processes:
            self._processes[mcp_id].terminate()
            del self._processes[mcp_id]
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
