# backend/context/indexer.py
import asyncio, hashlib, json, os
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import chromadb
from sentence_transformers import SentenceTransformer

IGNORE_PATTERNS = [
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.next', '.cache', '*.min.js', '*.min.css', '*.lock', '*.map',
    '*.png', '*.jpg', '*.gif', '*.svg', '*.ico', '*.woff', '*.ttf',
    'package-lock.json', 'pnpm-lock.yaml', '*.lockb'
]
CHUNK_LINES = 40
CHUNK_OVERLAP = 10
MAX_FILE_SIZE_KB = 500
# Dense/minified chunks max out the embedder's context and take minutes each
# on CPU; anything past this length adds no retrieval value
CHUNK_MAX_CHARS = 2000
HASH_SAVE_EVERY_N_FILES = 25

HASH_CACHE_PATH = Path.home() / '.forge' / 'index_hashes.json'

chroma_client = chromadb.PersistentClient(
    path=str(Path.home() / '.forge' / 'chroma'),
    settings=chromadb.Settings(anonymized_telemetry=False),
)
embedder = SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)


class ContextEngine:
    def __init__(self):
        self._collection = chroma_client.get_or_create_collection('forge_index')
        self._observer = None
        self._status = {'status': 'idle', 'files_indexed': 0, 'total_files': 0}
        # filepath -> content hash, persisted so restarts skip unchanged files
        self._indexed_hashes: dict[str, str] = self._load_hash_cache()
        if self._collection.count() == 0:
            self._indexed_hashes = {}  # vector store was wiped; cache is stale
        self._loop: asyncio.AbstractEventLoop | None = None
        # Editors fire several save events per write; serialize re-index jobs
        # so concurrent runs for the same file can't race on delete+add
        self._index_lock = asyncio.Lock()

    @staticmethod
    def _load_hash_cache() -> dict[str, str]:
        try:
            data = json.loads(HASH_CACHE_PATH.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_hash_cache(self):
        try:
            HASH_CACHE_PATH.parent.mkdir(exist_ok=True)
            HASH_CACHE_PATH.write_text(json.dumps(self._indexed_hashes), encoding='utf-8')
        except Exception:
            pass  # cache is an optimization; never fail indexing over it

    async def start_watcher(self):
        pass  # observer started when workspace is indexed

    async def stop_watcher(self):
        if self._observer:
            self._observer.stop()

    async def index(self, workspace_path: str):
        self._loop = asyncio.get_running_loop()
        self._status['status'] = 'indexing'
        files = await asyncio.to_thread(self._collect_files, workspace_path)
        self._status['total_files'] = len(files)
        self._status['files_indexed'] = 0

        for filepath in files:
            await self._index_file(filepath)
            self._status['files_indexed'] += 1
            if self._status['files_indexed'] % HASH_SAVE_EVERY_N_FILES == 0:
                self._save_hash_cache()  # checkpoint so an interrupted pass still counts

        self._status['status'] = 'ready'
        self._save_hash_cache()
        self._start_file_watcher(workspace_path)

    def _collect_files(self, workspace_path: str) -> list[str]:
        result = []
        for root, dirs, files in os.walk(workspace_path):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if not self._is_ignored(d)]
            for f in files:
                fpath = os.path.join(root, f)
                if not self._is_ignored(f) and os.path.getsize(fpath) < MAX_FILE_SIZE_KB * 1024:
                    result.append(fpath)
        return result

    def _is_ignored(self, name: str) -> bool:
        import fnmatch
        return any(fnmatch.fnmatch(name, p) for p in IGNORE_PATTERNS)

    async def _index_file(self, filepath: str):
        # Embedding is CPU-bound; keep it off the event loop so the API stays responsive
        async with self._index_lock:
            await asyncio.to_thread(self._index_file_sync, filepath)

    def _index_file_sync(self, filepath: str):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return

        content_hash = hashlib.md5(content.encode()).hexdigest()
        if self._indexed_hashes.get(filepath) == content_hash:
            return  # unchanged, skip

        # Remove old chunks for this file
        try:
            self._collection.delete(where={'file': filepath})
        except Exception:
            pass

        chunks = self._chunk_content(content, filepath)
        if not chunks:
            return

        texts = [c['content'] for c in chunks]
        embeddings = embedder.encode(texts, batch_size=32, show_progress_bar=False).tolist()

        self._collection.upsert(
            ids=[f'{filepath}:{c["start_line"]}' for c in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=[{'file': filepath, 'line': c['start_line']} for c in chunks],
        )
        self._indexed_hashes[filepath] = content_hash
        if self._status['status'] != 'indexing':
            self._save_hash_cache()  # watcher-triggered update; bulk index saves once at the end

    def _chunk_content(self, content: str, filepath: str) -> list[dict]:
        lines = content.split('\n')
        chunks = []
        i = 0
        while i < len(lines):
            end = min(i + CHUNK_LINES, len(lines))
            chunk_text = '\n'.join(lines[i:end])[:CHUNK_MAX_CHARS]
            if chunk_text.strip():
                chunks.append({'content': chunk_text, 'start_line': i + 1})
            i += CHUNK_LINES - CHUNK_OVERLAP
        return chunks

    def search(self, query: str, k: int = 8) -> list[dict]:
        if self._collection.count() == 0:
            return []
        embedding = embedder.encode([query]).tolist()
        results = self._collection.query(query_embeddings=embedding, n_results=min(k, self._collection.count()))
        output = []
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            output.append({'content': doc, 'file': meta['file'], 'line': meta['line']})
        return output

    def get_status(self) -> dict:
        return self._status

    def _start_file_watcher(self, workspace_path: str):
        handler = ForgeFileEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, workspace_path, recursive=True)
        self._observer.start()

    async def summarize_repo(self, workspace_path: str) -> str:
        # Collect representative files: README, main files, config files
        key_files = []
        for pattern in ['README.md', 'package.json', 'pyproject.toml', 'setup.py', 'main.py', 'index.ts', 'app.py']:
            candidates = list(Path(workspace_path).rglob(pattern))
            if candidates:
                key_files.append(candidates[0])

        file_contents = []
        for f in key_files[:10]:
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')[:2000]
                file_contents.append(f'## {f.name}\n{content}')
            except Exception:
                pass

        return '\n\n'.join(file_contents)


class ForgeFileEventHandler(FileSystemEventHandler):
    def __init__(self, engine: ContextEngine):
        self.engine = engine

    def on_modified(self, event):
        # Watchdog callbacks run on a non-asyncio thread; create_task would fail there
        if not event.is_directory and self.engine._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self.engine._index_file(event.src_path), self.engine._loop
            )
