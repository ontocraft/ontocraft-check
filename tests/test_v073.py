"""0.7.3: `ontocraft-check mcp` 로 MCP 서버를 띄웁니다."""

from ontocraft_check import cli, mcp_server


def test_mcp_subcommand_runs_server(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    called = []
    monkeypatch.setattr(mcp_server, "main", lambda: called.append(1) or 0)
    assert cli.main(["mcp"]) == 0
    assert called == [1]


def test_file_named_mcp_is_read_as_ontology(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mcp").write_text("not turtle", encoding="utf-8")
    called = []
    monkeypatch.setattr(mcp_server, "main", lambda: called.append(1) or 0)
    assert cli.main(["mcp"]) == 2
    assert called == []
