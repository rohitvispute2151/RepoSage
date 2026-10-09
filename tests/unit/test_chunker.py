"""Unit tests for AST-based Python code chunking."""

from reposage.ingest.chunker import chunk_python


def test_chunk_functions_and_classes():
    """Verify function and class parsing with qualnames and signatures."""
    source = (
        "class Worker:\n"
        '    """Background processor."""\n'
        "    def run(self, task: str) -> bool:\n"
        "        return True\n\n"
        "def standalone_func():\n"
        "    pass\n"
    )

    chunks = chunk_python(path="src/worker.py", source=source, is_test=False)

    qualnames = [c.qualname for c in chunks]
    assert any("Worker" in q for q in qualnames)
    assert any("Worker.run" in q for q in qualnames)
    assert any("standalone_func" in q for q in qualnames)

    # Verify header formatting
    method_chunk = next(c for c in chunks if "Worker.run" in c.qualname)
    assert "# symbol: worker.Worker.run (method)" in method_chunk.content
    assert "# signature: def run(self, task: str) -> bool" in method_chunk.content


def test_chunk_syntax_error_fallback():
    """Verify that syntax errors fall back to single module chunk."""
    broken_source = "def incomplete_code(\n"
    chunks = chunk_python(path="broken.py", source=broken_source, is_test=False)
    assert len(chunks) == 1
    assert chunks[0].kind == "module_header"
