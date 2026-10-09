from __future__ import annotations

from pathlib import Path
from agents.schemas import RoleResult


class MockBackend:
    """Deterministic role fixtures. Measurements remain real outside unit tests."""
    def invoke(self, role: str, payload: dict, workspace: Path, artifacts: Path, case: str = "noop") -> RoleResult:
        if role == "planner":
            if case == "timeout":
                return RoleResult(status="timeout", error="Mock role timeout")
            if case == "malformed":
                return RoleResult(status="ok", output={"bad": "schema"})
            return RoleResult(status="ok", output={"schema_version": 1,
                "hypothesis": "Mock exercise of one focused change; no performance claim.",
                "change": "Apply the configured mock development fixture.",
                "risks": ["Fixture is not a real optimization strategy."], "approach": "other"})
        if role == "developer":
            edits = []
            if case in {"comment", "faster", "slower", "audit_failure"}:
                source = (workspace / "app" / "__init__.py").read_text()
                edits = [{"path": "app/__init__.py", "content": source + "\n# Mock candidate fixture.\n"}]
            elif case == "broken":
                edits = [{"path": "app/main.py", "content": "def broken(\n"}]
            elif case == "forbidden":
                edits = [{"path": "../tests/test_notes.py", "content": ""}]
            return RoleResult(status="ok", output={"schema_version": 1, "summary": f"Mock {case} fixture", "edits": edits})
        if case == "audit_failure":
            return RoleResult(status="agent_error", error="Mock terminal audit failure")
        return RoleResult(status="ok", output={"schema_version": 1,
            "interpretation": "Mock interpretation; use runner facts for conclusions.",
            "limitations": ["No live model was used."]})
