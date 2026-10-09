"""Graph execution nodes for RepoSage LangGraph agent."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from reposage.agent.budget import BudgetManager
from reposage.llm.client import ResilientLLM
from reposage.observability.tracing import Tracer
from reposage.sandbox.client import SandboxClient


@dataclass
class AgentDependencies:
    """Shared runtime dependencies injected into graph nodes."""

    db: AsyncSession
    llm: ResilientLLM
    budget: BudgetManager
    tracer: Tracer
    snapshot_root: Path
    sandbox_client: Optional[SandboxClient] = None
    event_sink: Optional[Callable[[str, str, dict[str, Any]], Any]] = None

    def emit_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Forward lifecycle and tool events to the event sink."""
        if self.event_sink:
            self.event_sink(task_id, event_type, payload)
