"""
Proves the custom-provider/model onboarding flow on ModelRouter: registering
a dynamic (non-hardcoded) provider with a base_url, adding a model under it,
and streaming through that model -- all with mocked provider clients and an
isolated sqlite db (no real API keys / network calls, no dependency on
main.py).

Run with:  python backend/tests/test_custom_models.py
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

# Isolate this test from the user's real ~/.forge/forge.db BEFORE importing db
# (directly or transitively via router.model_router).
import os
os.environ['FORGE_DB_PATH'] = str(Path(tempfile.mkdtemp(prefix='forge-test-db-')) / 'forge.db')

# backend/ must be on sys.path so `from router.model_router import ModelRouter`
# resolves the same way it does inside the backend package itself. Do NOT
# import main.py.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db import init_db  # noqa: E402
from router.model_router import ModelRouter  # noqa: E402

NVIDIA_BASE_URL = 'https://integrate.api.nvidia.com/v1'


def _make_chunk(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


class FakeAsyncStream:
    def __init__(self, contents: list[str]):
        self._contents = list(contents)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._contents:
            raise StopAsyncIteration
        return _make_chunk(self._contents.pop(0))


def test_register_provider_with_base_url() -> bool:
    ok = True
    router = ModelRouter()
    router.register_provider('nvidia_test', 'sk-fake-key', NVIDIA_BASE_URL)

    client = router._get_client('nvidia_test')
    client_base_url = str(client.base_url).rstrip('/')
    expected = NVIDIA_BASE_URL.rstrip('/')
    if client_base_url != expected:
        print(f"FAIL: expected client.base_url {expected!r}, got {client_base_url!r}")
        ok = False
    else:
        print(f"PASS: _get_client('nvidia_test') returns a client with base_url {client_base_url!r}")

    from db import get_session
    from db.models import Provider
    with get_session() as db:
        row = db.query(Provider).filter_by(id='nvidia_test').first()
    if row is None or row.base_url != NVIDIA_BASE_URL:
        print(f"FAIL: expected a persisted Provider row for 'nvidia_test' with base_url {NVIDIA_BASE_URL!r}, got {row}")
        ok = False
    else:
        print(f"PASS: Provider row for 'nvidia_test' persisted with base_url {row.base_url!r}")

    # A fresh ModelRouter instance (new object, same db) must load the
    # dynamic provider back via _load_settings().
    router2 = ModelRouter()
    if 'nvidia_test' not in router2._dynamic_providers:
        print(f"FAIL: expected fresh ModelRouter to load 'nvidia_test' into _dynamic_providers, got {router2._dynamic_providers}")
        ok = False
    else:
        print("PASS: fresh ModelRouter instance loads the dynamic provider back from the db")

    client2 = router2._get_client('nvidia_test')
    client2_base_url = str(client2.base_url).rstrip('/')
    if client2_base_url != expected:
        print(f"FAIL: expected fresh router's client.base_url {expected!r}, got {client2_base_url!r}")
        ok = False
    else:
        print(f"PASS: fresh ModelRouter's _get_client('nvidia_test') also returns base_url {client2_base_url!r}")

    return ok


def test_add_model() -> bool:
    ok = True
    router = ModelRouter()
    router.register_provider('nvidia', 'sk-fake-key', NVIDIA_BASE_URL)
    result = router.add_model('nvidia', 'z-ai/glm-5.2', display_name='GLM 5.2 (NVIDIA)', is_free=False, context_window=8192)

    if result.get('id') != 'nvidia/z-ai/glm-5.2':
        print(f"FAIL: expected add_model() result id 'nvidia/z-ai/glm-5.2', got {result}")
        ok = False
    else:
        print(f"PASS: add_model() returned id {result['id']!r}")

    models = router.list_models()
    found = next((m for m in models if m['id'] == 'nvidia/z-ai/glm-5.2'), None)
    if found is None:
        print(f"FAIL: expected list_models() to include 'nvidia/z-ai/glm-5.2', got ids={[m['id'] for m in models]}")
        ok = False
    else:
        print(f"PASS: list_models() includes 'nvidia/z-ai/glm-5.2' ({found['display_name']!r})")

    return ok


async def _run_stream_split_test() -> bool:
    ok = True
    router = ModelRouter()
    router._log_usage = lambda *args, **kwargs: None  # type: ignore[method-assign]
    router.register_provider('nvidia', 'sk-fake-key', NVIDIA_BASE_URL)
    router.add_model('nvidia', 'z-ai/glm-5.2', display_name='GLM 5.2 (NVIDIA)')

    received_kwargs: dict = {}

    async def fake_create(**kwargs):
        received_kwargs.update(kwargs)
        return FakeAsyncStream(['ok'])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    router._get_client = lambda provider: fake_client  # type: ignore[method-assign]

    collected = []
    async for raw in router.stream(
        messages=[{'role': 'user', 'content': 'hello'}],
        model_id='nvidia/z-ai/glm-5.2',
        context_chunks=[],
        auto_fallback=False,
    ):
        payload = json.loads(raw)
        if 'content' in payload:
            collected.append(payload['content'])

    if received_kwargs.get('model') != 'z-ai/glm-5.2':
        print(f"FAIL: expected fake create() to receive model='z-ai/glm-5.2' (first-slash split preserved), got model={received_kwargs.get('model')!r}")
        ok = False
    else:
        print(f"PASS: stream() split 'nvidia/z-ai/glm-5.2' into provider='nvidia', model='z-ai/glm-5.2' (create() received model={received_kwargs.get('model')!r})")

    return ok


def main() -> int:
    init_db()
    ok = True
    ok &= test_register_provider_with_base_url()
    ok &= test_add_model()
    ok &= asyncio.run(_run_stream_split_test())

    if ok:
        print("PASS: all custom-provider/model assertions succeeded")
        return 0
    print("FAIL: one or more custom-provider/model assertions failed")
    return 1


if __name__ == '__main__':
    sys.exit(main())
