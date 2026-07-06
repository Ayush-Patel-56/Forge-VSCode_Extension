"""
Scripted proof of one-click MCP install/uninstall, driven directly against
MCPManager (no HTTP, no main.py import).

Run with:  python backend/tests/test_mcp_manager.py

Notes:
  - This spawns a *real* `npx @modelcontextprotocol/server-filesystem` process
    on Windows (exercising the shutil.which('npx') -> npx.cmd resolution fix).
    The first run may need to download the package over npm, so we just await
    manager.install(...) and let it take as long as it needs (no artificial
    timeout on our end beyond the health check MCPManager itself does).
  - Uses the same sqlite db (~/.forge/forge.db) the running backend uses, via
    db.init_db()/get_session, so mcp_servers rows persist across runs. That's
    fine here: install()/uninstall() upsert the same row, so re-running the
    script is idempotent.
"""
import asyncio
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Isolate this test from the user's real ~/.forge/forge.db BEFORE importing db:
# install/uninstall below would otherwise flip the user's is_installed flags.
os.environ['FORGE_DB_PATH'] = str(Path(tempfile.mkdtemp(prefix='forge-test-db-')) / 'forge.db')

# backend/ must be on sys.path so `from mcp.manager import MCPManager` resolves
# the same way it does inside the backend package itself. Do NOT import main.py.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db import init_db  # noqa: E402
from mcp.manager import MCPManager  # noqa: E402


async def run_test() -> bool:
    ok = True
    init_db()
    manager = MCPManager()
    workspace = Path(tempfile.mkdtemp(prefix="forge-mcp-test-"))

    try:
        # --- Step 1: install filesystem MCP (real npx spawn on Windows) -------
        result = await manager.install('filesystem', {'WORKSPACE_PATH': str(workspace)})
        if result.get('status') != 'ready':
            print(f"FAIL: install('filesystem', ...) expected status 'ready', got {result}")
            ok = False
        else:
            print("PASS: install('filesystem', {'WORKSPACE_PATH': ...}) returned status 'ready'")

        # --- Step 2: list_all() shows filesystem as running --------------------
        listing = manager.list_all()
        fs_entry = next((m for m in listing if m['id'] == 'filesystem'), None)
        if fs_entry is None or fs_entry.get('status') != 'running':
            print(f"FAIL: expected list_all() to show filesystem status 'running', got {fs_entry}")
            ok = False
        else:
            print("PASS: list_all() shows filesystem status 'running'")

        # --- Step 2b: simulate a backend restart -- kill the process directly
        # (not via uninstall()) so the db still says is_installed=True but
        # nothing is running, then confirm start() can bring it back. --------
        proc = manager._processes.get('filesystem')
        if proc is None:
            print("FAIL: expected manager._processes['filesystem'] to exist before simulated restart")
            ok = False
        else:
            proc.terminate()
            proc.wait(timeout=10)

            listing_stopped = manager.list_all()
            fs_entry_stopped = next((m for m in listing_stopped if m['id'] == 'filesystem'), None)
            if fs_entry_stopped is None or fs_entry_stopped.get('status') != 'installed':
                print(f"FAIL: expected list_all() to show filesystem status 'installed' after killing its process, got {fs_entry_stopped}")
                ok = False
            else:
                print("PASS: list_all() shows filesystem status 'installed' after simulated backend restart")

            start_result = await manager.start('filesystem', str(workspace))
            if start_result.get('status') != 'ready':
                print(f"FAIL: start('filesystem', ...) expected status 'ready', got {start_result}")
                ok = False
            else:
                print("PASS: start('filesystem', workspace) returned status 'ready'")

            listing_restarted = manager.list_all()
            fs_entry_restarted = next((m for m in listing_restarted if m['id'] == 'filesystem'), None)
            if fs_entry_restarted is None or fs_entry_restarted.get('status') != 'running':
                print(f"FAIL: expected list_all() to show filesystem status 'running' after start(), got {fs_entry_restarted}")
                ok = False
            else:
                print("PASS: list_all() shows filesystem status 'running' again after start()")

        # --- Step 2c: start() on a never-installed id returns an error dict,
        # not an exception. -------------------------------------------------
        never_installed_result = await manager.start('memory', str(workspace))
        if never_installed_result.get('status') != 'error':
            print(f"FAIL: start('memory', ...) on a never-installed MCP expected status 'error', got {never_installed_result}")
            ok = False
        else:
            print(f"PASS: start('memory', ...) on a never-installed MCP returned error status: {never_installed_result.get('error')}")

        # --- Step 3: uninstall stops the process --------------------------------
        proc = manager._processes.get('filesystem')
        if proc is None:
            print("FAIL: expected manager._processes['filesystem'] to exist before uninstall")
            ok = False
        else:
            await manager.uninstall('filesystem')
            await asyncio.sleep(1.0)
            if proc.poll() is None:
                print("FAIL: expected filesystem process to be terminated after uninstall(), but it is still running")
                ok = False
            else:
                print(f"PASS: filesystem process terminated after uninstall() (exit code {proc.poll()})")

            listing_after = manager.list_all()
            fs_entry_after = next((m for m in listing_after if m['id'] == 'filesystem'), None)
            if fs_entry_after is None or fs_entry_after.get('status') == 'running':
                print(f"FAIL: expected list_all() to no longer show filesystem as 'running' after uninstall, got {fs_entry_after}")
                ok = False
            else:
                print(f"PASS: list_all() no longer shows filesystem as 'running' after uninstall (status={fs_entry_after.get('status')})")

        # --- Step 4: errors are returned as status, not raised exceptions ------
        unknown_result = await manager.install('unknown-mcp', {})
        if unknown_result.get('status') != 'error':
            print(f"FAIL: install('unknown-mcp', {{}}) expected status 'error', got {unknown_result}")
            ok = False
        else:
            print(f"PASS: install('unknown-mcp', {{}}) returned error status: {unknown_result.get('error')}")

        postgres_result = await manager.install('postgres', {})
        if postgres_result.get('status') != 'error' or 'DATABASE_URL' not in (postgres_result.get('error') or ''):
            print(f"FAIL: install('postgres', {{}}) expected error mentioning missing DATABASE_URL config, got {postgres_result}")
            ok = False
        else:
            print(f"PASS: install('postgres', {{}}) returned error mentioning missing config: {postgres_result.get('error')}")

        return ok
    finally:
        # Ensure no orphan node/npx processes survive this script, even on failure.
        try:
            await manager.stop_all()
        except Exception:
            pass
        for proc in list(manager._processes.values()):
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    ok = asyncio.run(run_test())
    if ok:
        print("PASS: all MCP install/uninstall assertions succeeded")
        return 0
    print("FAIL: one or more MCP install/uninstall assertions failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
