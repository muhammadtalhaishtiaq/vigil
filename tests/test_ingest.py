"""/ingest → wiki notes → context grounding (mocked LLM, temp workspace)."""

import io
import sys

import pytest

import agent_core
import agent_pipeline as ap
import tools
import vigil_cli


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "financials.md").write_text("Revenue $1.2M. 40% EUR exposure.")
    (docs / "contracts.txt").write_text("MegaCorp is 35% of revenue.")
    monkeypatch.setenv("VIGIL_WORKSPACE", str(tmp_path))
    return tmp_path


def test_ingest_writes_wiki_notes(workspace, monkeypatch, capsys):
    monkeypatch.setattr(
        agent_core.DOC_DISTILLER, "run",
        lambda content, **k: "## Summary\n- distilled: " + content[:40],
    )
    vigil_cli._cmd_ingest()
    out = capsys.readouterr().out
    assert "2/2 distilled" in out

    wiki = tools.workspace_dir("wiki")
    notes = sorted(p.name for p in wiki.glob("*.md"))
    assert notes == ["contracts.md", "financials.md"]
    body = (wiki / "financials.md").read_text()
    assert "distilled from financials.md" in body      # provenance header
    assert "index" in body                             # honest framing
    assert "financials.md" in body


def test_ingest_handles_empty_workspace(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VIGIL_WORKSPACE", str(tmp_path / "empty"))
    vigil_cli._cmd_ingest()
    assert "No documents found" in capsys.readouterr().out


def test_ingest_survives_distiller_failure(workspace, monkeypatch, capsys):
    monkeypatch.setattr(
        agent_core.DOC_DISTILLER, "run",
        lambda content, **k: "[DOC DISTILLER UNAVAILABLE — error]",
    )
    vigil_cli._cmd_ingest()
    out = capsys.readouterr().out
    assert "distillation failed" in out
    assert not list(tools.workspace_dir("wiki").glob("*.md"))


class TestWikiContext:
    def test_empty_without_wiki(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VIGIL_WORKSPACE", str(tmp_path / "none"))
        assert ap._wiki_context() == ""

    def test_notes_are_loaded_and_framed(self, workspace):
        wiki = tools.workspace_dir("wiki")
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "financials.md").write_text("## Key numbers\n- Revenue: $1.2M")
        ctx = ap._wiki_context()
        assert "COMPANY KNOWLEDGE BASE" in ctx
        assert "Revenue: $1.2M" in ctx

    def test_pipeline_feeds_wiki_to_orchestrator(self, workspace, mock_llm):
        wiki = tools.workspace_dir("wiki")
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "note.md").write_text("- MegaCorp concentration risk 35%")

        seen = {}

        def create(**kw):
            system = next(
                (m["content"] for m in kw["messages"] if m["role"] == "system"), "")
            if "Orchestrator" in system:
                seen["orch_input"] = kw["messages"][-1]["content"]
            from tests.conftest import make_response
            return make_response(content='{"intent_type": "MARKET_PULSE", '
                                         '"verdict": "calm"}')

        mock_llm(create)
        ap.run_pipeline("quick pulse please")
        assert "COMPANY KNOWLEDGE BASE" in seen["orch_input"]
        assert "MegaCorp concentration" in seen["orch_input"]
