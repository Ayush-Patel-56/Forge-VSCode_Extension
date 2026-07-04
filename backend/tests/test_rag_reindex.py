# backend/tests/test_rag_reindex.py
"""
Scripted proof of the index -> search -> re-index flow, driven directly against
ContextEngine (no HTTP, no main.py import).

Run with:  python backend/tests/test_rag_reindex.py

Notes:
  - Importing context.indexer loads the real embedding model (nomic-embed-text-v1.5),
    which takes ~20s on first import even though it's cached locally afterwards.
  - This uses the *real* ChromaDB persisted at ~/.forge/chroma (the same store the
    running backend uses), so we use a uniquely-named temp workspace to avoid id
    collisions with any other indexed content, and delete our chunks on cleanup.
"""
import asyncio
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

# backend/ must be on sys.path so `from context.indexer import ContextEngine`
# resolves the same way it does inside the backend package itself.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from context.indexer import ContextEngine  # noqa: E402


def _write_files(workspace: Path) -> tuple[Path, Path, Path]:
    file_a = workspace / "grades.py"
    file_a.write_text(
        "def calculate_student_gpa(grades):\n"
        "    \"\"\"Average a list of numeric grade points into a GPA.\"\"\"\n"
        "    if not grades:\n"
        "        return 0.0\n"
        "    return sum(grades) / len(grades)\n",
        encoding="utf-8",
    )

    file_b = workspace / "roster.py"
    file_b.write_text(
        "class StudentRoster:\n"
        "    \"\"\"Tracks enrolled students for a class section.\"\"\"\n"
        "    def __init__(self):\n"
        "        self.students = []\n"
        "\n"
        "    def enroll(self, name):\n"
        "        self.students.append(name)\n",
        encoding="utf-8",
    )

    file_c = workspace / "notes.md"
    file_c.write_text(
        "# Course Notes\n\nThis directory holds miscellaneous course planning notes.\n",
        encoding="utf-8",
    )

    return file_a, file_b, file_c


def _cleanup_chunks(engine: ContextEngine, filepaths: list[Path]) -> None:
    for fp in filepaths:
        try:
            engine._collection.delete(where={"file": str(fp)})
        except Exception:
            pass


async def run_test() -> bool:
    ok = True

    workspace = Path(tempfile.mkdtemp(prefix=f"forge_rag_test_{uuid.uuid4().hex[:8]}_"))
    engine = ContextEngine()
    all_test_files: list[Path] = []

    try:
        file_a, file_b, file_c = _write_files(workspace)
        all_test_files.extend([file_a, file_b, file_c])

        # --- Step 1: initial index ------------------------------------------------
        await engine.index(str(workspace))

        status = engine.get_status()
        if status.get("status") != "ready":
            print(f"FAIL: expected status 'ready' after index(), got {status!r}")
            ok = False
        else:
            print(f"PASS: engine status is 'ready' after initial index ({status['files_indexed']}/{status['total_files']} files)")

        results = engine.search("gpa calculation", 4)
        matched_gpa_file = any(Path(r["file"]) == file_a for r in results)
        if not matched_gpa_file:
            print(f"FAIL: expected a chunk from {file_a} in search('gpa calculation'), got files={[r['file'] for r in results]}")
            ok = False
        else:
            print(f"PASS: search('gpa calculation') returned a chunk from {file_a.name}")

        # --- Step 2: modify a file, deterministically re-index just that file -----
        distinctive_snippet = (
            "\n\ndef fetch_attendance_report(section_id):\n"
            "    \"\"\"Fetch the attendance report for a class section id.\"\"\"\n"
            "    return {\"section_id\": section_id, \"present\": [], \"absent\": []}\n"
        )
        with open(file_b, "a", encoding="utf-8") as f:
            f.write(distinctive_snippet)

        # Call _index_file directly rather than relying on the watchdog observer's
        # timing, so this test is deterministic.
        await engine._index_file(str(file_b))

        results2 = engine.search("fetch attendance report for a section", 4)
        matched_attendance_file = any(Path(r["file"]) == file_b for r in results2)
        if not matched_attendance_file:
            print(f"FAIL: expected a chunk from {file_b} in search('fetch attendance report...'), got files={[r['file'] for r in results2]}")
            ok = False
        else:
            print(f"PASS: search('fetch attendance report...') returned a chunk from {file_b.name} after targeted re-index")

        # --- Step 3: watcher smoke check -------------------------------------------
        if engine._observer is None:
            print("FAIL: expected engine._observer to be set after index() started the file watcher")
            ok = False
        else:
            print("PASS: file watcher observer was started by index()")

        return ok
    finally:
        # Stop the watcher first so it can't race with our cleanup.
        try:
            await engine.stop_watcher()
        except Exception:
            pass

        _cleanup_chunks(engine, all_test_files)
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    ok = asyncio.run(run_test())
    if ok:
        print("PASS: all RAG index/search/re-index assertions succeeded")
        return 0
    print("FAIL: one or more RAG index/search/re-index assertions failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
