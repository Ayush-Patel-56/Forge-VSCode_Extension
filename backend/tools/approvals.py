# backend/tools/approvals.py
"""Approval registry for the terminal__run_command tool, plus the executor
that wires an SSE event queue to a pending approval.

Flow:
  1. request_approval() pushes {"event":"approval_request", ...} onto the
     per-request event_queue (drained by ModelRouter._drain_queue_while while
     the tool executor task is in flight -- see model_router.py), then waits
     up to timeout_s for a decision.
  2. The /api/chat/approval endpoint in main.py calls resolve_approval() with
     the user's decision, which wakes the waiter.
  3. On 'allow', run_terminal_with_approval() actually executes the command.
     On timeout, it's treated as 'deny'.
"""
import asyncio
import itertools

from tools.terminal import run_command

DEFAULT_TIMEOUT_S = 300.0

_id_counter = itertools.count(1)


class _PendingApproval:
    __slots__ = ('event', 'decision', 'detail')

    def __init__(self):
        self.event = asyncio.Event()
        self.decision: str | None = None
        self.detail: str | None = None


_pending: dict[str, _PendingApproval] = {}


def new_approval_id() -> str:
    return f'ap_{next(_id_counter)}'


def resolve_approval(approval_id: str, decision: str, detail: str | None = None) -> bool:
    """Called from the /api/chat/approval endpoint. Returns False if the
    approval_id is unknown (already resolved, timed out, or bogus)."""
    pending = _pending.get(approval_id)
    if pending is None:
        return False
    pending.decision = decision
    pending.detail = detail
    pending.event.set()
    return True


async def request_approval(
    event_queue: asyncio.Queue, command: str, cwd: str, timeout_s: float = DEFAULT_TIMEOUT_S
) -> tuple[str, str | None]:
    """Push an approval_request event and wait for a decision.
    Returns (decision, detail); ('deny', None) on timeout."""
    approval_id = new_approval_id()
    pending = _PendingApproval()
    _pending[approval_id] = pending
    try:
        await event_queue.put({
            'event': 'approval_request', 'id': approval_id, 'command': command, 'cwd': cwd,
        })
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return 'deny', None
        return pending.decision or 'deny', pending.detail
    finally:
        _pending.pop(approval_id, None)


async def run_terminal_with_approval(event_queue: asyncio.Queue, workspace_path: str, arguments: dict) -> dict:
    """The terminal__run_command tool executor. Requests approval via
    event_queue, then runs (or skips) the command based on the decision."""
    command = (arguments or {}).get('command') or ''
    cwd = (arguments or {}).get('cwd') or workspace_path or '.'

    if not command.strip():
        return {'text': 'No command was provided.'}

    decision, detail = await request_approval(event_queue, command, cwd)

    if decision == 'allow':
        result = await run_command(command, cwd)
        return {'text': f"exit_code={result['exit_code']}\n{result['output']}"}
    if decision == 'other':
        return {'text': f'User did not run the command and says: {detail or ""}'}
    return {'text': 'User declined to run this command.'}
