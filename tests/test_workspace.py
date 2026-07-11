"""Workspace docs tool: search, read, traversal safety, honest empty states."""

import pytest

import agent_core
import tools


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A temp workspace with two docs."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "financials-q2.md").write_text(
        "# Q2 financials\n\nRevenue was $1.2M, with 40% EUR exposure from "
        "European SMB clients.\n\nBurn rate is $80k/month with 14 months runway.",
        encoding="utf-8",
    )
    (docs / "contracts.txt").write_text(
        "Top client: MegaCorp, 35% of revenue. Contract renews in October.",
        encoding="utf-8",
    )
    (docs / "ignore.pdf").write_bytes(b"%PDF fake")  # unsupported type
    monkeypatch.setenv("VIGIL_WORKSPACE", str(tmp_path))
    return tmp_path


class TestSearch:
    def test_finds_relevant_snippets(self, workspace):
        out = tools._fmt_doc_search("EUR exposure revenue")
        assert "financials-q2.md" in out
        assert "40% EUR" in out
        assert out.startswith("<<EXTERNAL_DATA")

    def test_lists_docs_when_no_match(self, workspace):
        out = tools._fmt_doc_search("quantum blockchain")
        assert "No matches" in out
        assert "financials-q2.md" in out  # tells the agent what IS available

    def test_honest_when_workspace_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VIGIL_WORKSPACE", str(tmp_path / "nowhere"))
        out = tools._fmt_doc_search("revenue")
        assert "No company documents" in out

    def test_unsupported_types_excluded(self, workspace):
        names = [p.name for p in tools.list_company_docs()]
        assert names == ["contracts.txt", "financials-q2.md"]


class TestRead:
    def test_reads_full_doc_enveloped(self, workspace):
        out = tools._fmt_doc_read("contracts.txt")
        assert "MegaCorp" in out
        assert out.startswith("<<EXTERNAL_DATA")

    def test_path_traversal_blocked(self, workspace):
        for evil in ("../../etc/passwd", "/etc/passwd", "..\\secrets.md"):
            out = tools._fmt_doc_read(evil)
            assert "not an available company document" in out or "not found" in out
            assert "root:" not in out

    def test_missing_doc_lists_available(self, workspace):
        out = tools._fmt_doc_read("nope.md")
        assert "not found" in out
        assert "financials-q2.md" in out


def test_signal_harvester_has_docs_tools():
    names = {t.name for t in agent_core.AGENTS["signal_harvester"].tools}
    assert {"search_company_docs", "read_company_doc"} <= names
