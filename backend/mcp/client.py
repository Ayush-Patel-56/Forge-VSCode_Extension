# backend/mcp/client.py
"""Minimal MCP (Model Context Protocol) client over stdio.

Speaks JSON-RPC 2.0 with newline-delimited JSON (one message per line) to a
spawned MCP server process. The underlying subprocess.Popen pipes are
blocking, so all I/O here runs on a background reader thread + queue; the
manager calls the (blocking) public methods via asyncio.to_thread from async
code instead of rewriting process management around asyncio subprocesses.
"""
import subprocess
import json
import threading
import queue
import itertools


class MCPError(Exception):
    """Raised when an MCP server returns a JSON-RPC error response."""


class MCPClient:
    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self._id_counter = itertools.count(1)
        self._pending: dict[int, "queue.Queue"] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._tools_cache: list | None = None

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

    # -- transport -----------------------------------------------------

    def _read_loop(self):
        stdout = self.proc.stdout
        if stdout is None:
            return
        while True:
            try:
                line = stdout.readline()
            except Exception:
                break
            if not line:
                break  # EOF - process closed stdout (dead or shutting down)
            try:
                text = line.decode('utf-8', errors='ignore').strip()
            except AttributeError:
                text = line.strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except Exception:
                # Server log/banner line on stdout that isn't JSON-RPC - skip.
                continue

            msg_id = msg.get('id')
            if msg_id is None:
                continue  # notification from the server - nothing to route it to

            with self._pending_lock:
                q = self._pending.pop(msg_id, None)
            if q is not None:
                q.put(msg)

    def _send(self, obj: dict):
        data = (json.dumps(obj) + '\n').encode('utf-8')
        with self._write_lock:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()

    def _request(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        msg_id = next(self._id_counter)
        q: "queue.Queue" = queue.Queue()
        with self._pending_lock:
            self._pending[msg_id] = q

        self._send({'jsonrpc': '2.0', 'id': msg_id, 'method': method, 'params': params})

        try:
            resp = q.get(timeout=timeout)
        except queue.Empty:
            with self._pending_lock:
                self._pending.pop(msg_id, None)
            raise TimeoutError(f'MCP request "{method}" timed out after {timeout}s')

        if 'error' in resp:
            raise MCPError(f'MCP server error on "{method}": {resp["error"]}')
        return resp.get('result', {}) or {}

    def _notify(self, method: str, params: dict | None = None):
        self._send({'jsonrpc': '2.0', 'method': method, 'params': params or {}})

    # -- protocol --------------------------------------------------------

    def initialize(self) -> dict:
        result = self._request('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'forge', 'version': '0.1.0'},
        })
        self._notify('notifications/initialized', {})
        return result

    def list_tools(self, use_cache: bool = True) -> list:
        if use_cache and self._tools_cache is not None:
            return self._tools_cache
        result = self._request('tools/list', {})
        tools = result.get('tools', []) or []
        self._tools_cache = tools
        return tools

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self._request('tools/call', {'name': name, 'arguments': arguments})
        text_parts = []
        for entry in (result.get('content') or []):
            if isinstance(entry, dict) and entry.get('type') == 'text':
                text_parts.append(entry.get('text', ''))
        result['text'] = '\n'.join(text_parts)
        return result

    def close(self):
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
