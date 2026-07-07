# backend/tools/terminal.py
"""Approval-gated shell command execution. run_command() itself does not gate
on approval -- that's handled one layer up in backend/tools/approvals.py --
it just spawns, captures, and caps output."""
import asyncio

MAX_OUTPUT_CHARS = 8000


async def run_command(command: str, cwd: str, timeout_s: int = 60) -> dict:
    """Run `command` in a shell under `cwd`, capturing combined stdout+stderr
    (capped to MAX_OUTPUT_CHARS, with a truncation note). Kills the process
    and reports on timeout. Never raises for a failing command -- exit_code
    carries that information."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd or None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as e:
        return {'exit_code': -1, 'output': f'Failed to start command: {e}'}

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        return {'exit_code': -1, 'output': f'Command timed out after {timeout_s}s and was killed.'}

    output = stdout.decode(errors='replace') if stdout else ''
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + '\n...[output truncated]'

    return {'exit_code': proc.returncode, 'output': output}
