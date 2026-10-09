"""Shared test fixtures for RepoSage unit and integration test suites."""

from collections.abc import AsyncGenerator
from pathlib import Path
import shutil
import tempfile
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from reposage.api.deps import get_db
from reposage.api.main import app
from reposage.db.models import Base
from reposage.llm.client import ResilientLLM
from reposage.llm.ledger import CostLedger
from reposage.llm.providers.fake import FakeProvider


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository directory with real source and test files."""
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    src_dir = repo_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    # Source file with retry logic
    (src_dir / "http.py").write_text(
        '"""HTTP Client Module."""\n\n'
        "class Client:\n"
        '    """HTTP Client with retry handler."""\n'
        "    def __init__(self, retries: int = 3):\n"
        "        self.retries = retries\n\n"
        "    def send(self, url: str) -> bool:\n"
        '        """Send request with retry logic."""\n'
        "        if self.retries <= 0:\n"
        "            return False\n"
        "        return True\n\n"
        "def compute_backoff(attempt: int) -> float:\n"
        '    """Compute exponential backoff interval."""\n'
        "    return 0.5 * (2 ** attempt)\n",
        encoding="utf-8",
    )

    # Test file
    (tests_dir / "test_http.py").write_text(
        "from src.http import Client, compute_backoff\n\n"
        "def test_retry():\n"
        "    client = Client(retries=3)\n"
        "    assert client.send('http://example.com') is True\n\n"
        "def test_backoff():\n"
        "    assert compute_backoff(1) == 1.0\n",
        encoding="utf-8",
    )

    (repo_dir / "README.md").write_text("# Sample Repo\nTest project.", encoding="utf-8")
    return repo_dir


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """In-memory SQLite async session for isolated tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def fake_llm() -> ResilientLLM:
    """Fake resilient LLM provider with recorded mock behaviors."""
    fake_provider = FakeProvider()
    return ResilientLLM(
        providers={"fake": fake_provider},
        chain=[("fake", "default")],
        breakers={},
        ledger=CostLedger(),
    )


@pytest_asyncio.fixture
async def client(async_db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client pointing to FastAPI app with overridden DB session."""
    async def override_get_db():
        yield async_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
