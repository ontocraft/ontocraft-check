"""0.3.0에서 더한 기능: 이름 바꾸기, 내장 등록부(--registry builtin), 에이전트 도구, MCP 서버."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from helpers import f, local, run
from ontocraft_check import TOOL_TITLE, __version__
from ontocraft_check import tools as T
from ontocraft_check.checks.registry import BUILTIN_REGISTRY, builtin_manifest, list_domains
from ontocraft_check.cli import main
from ontocraft_check.render import RULE_TITLES, render

ROOT = Path(__file__).resolve().parents[1]
TERM_KEYS = {"id", "ko", "en", "alt", "definition", "category", "broader", "related", "refs", "example"}
WRONG_DOMAIN = {
    ("Measurement", "semiconductor", "fab-metrology"),
    ("Service", "physical-ai", "ros-service"),
    ("Sensor", "smartcity", "city-iot-sensor"),
    ("Observation", "smartcity", "sensor-observation"),
    ("ContainerCargo", "port", "shipping-container"),
}


def triples(report, rule):
    return {(local(x.target), x.detail["domain"], x.detail["term_id"]) for x in report.findings if x.rule == rule}


# 이름과 머리

def test_new_name_in_report_heads():
    r = run(f("clean.ttl"))
    md = render(r, "md")
    assert md.startswith(f"# {TOOL_TITLE} 보고서")
    assert TOOL_TITLE == "OntoCraft 온톨로지 검사기(ontocraft-check)"
    assert f"ontocraft-check {__version__}으로 만들었습니다" in md
    assert "<title>ontocraft-check 보고서:" in render(r, "html")
    d = json.loads(render(r, "json"))
    assert d["tool"] == "ontocraft-check" and d["version"] == "0.3.0"


def test_cli_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "ontocraft-check 0.3.0" in capsys.readouterr().out


# 내장 등록부

def test_builtin_snapshot_is_published_only_and_clean():
    m = builtin_manifest()
    assert m["license"] == "CC BY 4.0" and m["snapshot"]
    assert m["uri_template"] == "https://w3id.org/ontocraft/terms/{id}"
    files = sorted(p.name for p in BUILTIN_REGISTRY.glob("*.json") if p.name != "manifest.json")
    assert files == sorted(d["file"] for d in m["domains"])
    assert not {"health", "stock"} & {d["id"] for d in m["domains"]}  # 공개 보류 분야는 넣지 않습니다
    total = 0
    for name in files:
        data = json.loads((BUILTIN_REGISTRY / name).read_text(encoding="utf-8"))
        assert data["license"] == "CC BY 4.0" and data["registry"] == "OntoCraft 한국 산업 용어 등록부"
        assert "notes" not in data
        for t in data["terms"]:
            assert set(t) <= TERM_KEYS, (name, t["id"], set(t) - TERM_KEYS)
            assert t["id"] and t["ko"] and t["definition"]
        total += len(data["terms"])
    assert total == m["total_terms"]


def test_builtin_registry_matches_like_real_registry():
    r = run(f("maritime-like.ttl"), registry_dir="builtin", domains=["maritime"])
    assert WRONG_DOMAIN <= triples(r, "REG02")
    assert ("Vessel", "maritime", "ship") in triples(r, "REG01")
    assert not {t for t in triples(r, "REG01") if t[1] != "maritime"}
    assert r.inputs["registry"].startswith("builtin(내장 사본")
    assert "| 용어 등록부 | builtin(내장 사본" in render(r, "md")
    assert "manifest.json" not in r.stats["registry_files"]


def test_builtin_list_domains_skips_manifest():
    ids = {d["id"] for d in list_domains(BUILTIN_REGISTRY)}
    assert ids == {d["id"] for d in builtin_manifest()["domains"]}


def test_default_still_skips_registry():
    r = run(f("maritime-like.ttl"))
    assert "registry" not in r.ran


def test_cli_registry_builtin(tmp_path):
    out = tmp_path / "r.json"
    code = main([f("maritime-like.ttl"), "--registry", "builtin", "--domains", "maritime",
                 "--format", "json", "--out", str(out)])
    assert code in (0, 1)
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["summary"]["registry"]["status"] == "ran"
    assert any(x["rule"] == "REG01" and x["detail"]["term_id"] == "ship" for x in d["findings"])


def test_sync_registry_script(tmp_path):
    spec = importlib.util.spec_from_file_location("sync_registry", ROOT / "scripts" / "sync_registry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reg = tmp_path / "aki" / "data" / "registry"
    reg.mkdir(parents=True)
    (reg / "domains.json").write_text(json.dumps({"domains": [
        {"id": "a", "status": "published", "order": 2}, {"id": "b", "status": "draft", "order": 1}]}), encoding="utf-8")
    term = {"id": "x", "ko": "가", "en": "x", "alt": [], "definition": "뜻입니다.", "seed": "내부", "since": "0.1.0"}
    gone = {"id": "y", "ko": "나", "definition": "뜻", "status": "deprecated"}
    (reg / "a.json").write_text(json.dumps({"domain": {"id": "a", "name": "가"}, "notes": ["내부"],
                                            "version": "0.1.0", "terms": [term, gone]}), encoding="utf-8")
    (reg / "b.json").write_text(json.dumps({"domain": {"id": "b"}, "terms": [term]}), encoding="utf-8")
    out = tmp_path / "out"
    m = mod.build(tmp_path / "aki", "2026-01-01", out)
    assert [d["id"] for d in m["domains"]] == ["a"] and m["total_terms"] == 1
    a = json.loads((out / "a.json").read_text(encoding="utf-8"))
    assert a["terms"] == [{"id": "x", "ko": "가", "en": "x", "definition": "뜻입니다."}]
    assert a["snapshot"] == "2026-01-01" and "notes" not in a and not (out / "b.json").exists()


# 에이전트 도구(mcp 없이)

def test_tool_check_summary_from_path_and_content():
    s = T.check_ontology(f("pitfalls.ttl"))
    assert s["tool"] == "ontocraft-check"
    assert s["totals"]["치명"] >= 1
    assert len(s["critical_and_important"]) <= 20
    assert s["cannot_say"] and "skipped" in s
    text = Path(f("pitfalls.ttl")).read_text(encoding="utf-8")
    s2 = T.check_ontology(text)
    assert s2["totals"] == s["totals"]
    assert s2["source"].startswith("(ontology 본문 문자열")


def test_tool_check_formats_and_registry():
    d = T.check_ontology(f("maritime-like.ttl"), domains=["maritime"], format="json")
    assert d["summary"]["registry"]["status"] == "ran"
    s = T.check_ontology(f("maritime-like.ttl"), domains=["maritime"])
    assert s["registry_candidates"]["REG01"] >= 1 and s["registry_candidates"]["REG02"] >= 5
    s = T.check_ontology(f("maritime-like.ttl"), use_registry=False)
    assert "registry_candidates" not in s
    md = T.check_ontology(f("clean.ttl"), format="markdown")
    assert md.startswith(f"# {TOOL_TITLE} 보고서")


def test_tool_check_shacl_with_content_and_disable():
    s = T.check_ontology(f("clean.ttl"), data=Path(f("bad-data.ttl")).read_text(encoding="utf-8"),
                         shapes=f("clean-shapes.ttl"), use_registry=False)
    assert s["by_category"]["데이터 제약"]["status"] == "실행"
    s = T.check_ontology(f("pitfalls.ttl"), disable=["P06", "P19"], use_registry=False)
    assert s["disabled"] == ["P06", "P19"]
    assert not [x for x in s["critical_and_important"] if x["rule"] in ("P06", "P19")]


def test_tool_check_bad_inputs():
    with pytest.raises(T.InputError):
        T.check_ontology("/nope/missing.ttl")
    with pytest.raises(T.InputError):
        T.check_ontology(f("clean.ttl"), format="yaml")


def test_rules_tools():
    rules = T.list_rules()
    assert [r["rule"] for r in rules] == list(RULE_TITLES)
    p11 = T.explain_rule("p11")
    assert p11["severity"] == "important" and p11["fix"] and "OOPS!" in p11["note"]
    assert T.explain_rule("REG01")["severity_ko"] == "정보"
    with pytest.raises(T.InputError):
        T.explain_rule("P99")


def test_term_tools():
    hits = T.search_terms("선박")
    assert hits[0]["id"] == "ship" and hits[0]["match"] == "exact"
    assert hits[0]["uri"] == "https://w3id.org/ontocraft/terms/ship" and hits[0]["domain"] == "maritime"
    assert set(hits[0]) >= {"id", "ko", "en", "definition", "uri", "domain"}
    assert T.search_terms("배")[0]["id"] == "ship"  # 동의어
    assert T.search_terms("SHIP", domain="maritime")[0]["id"] == "ship"  # 영어, 대소문자 무시
    assert len(T.search_terms("선", limit=3)) == 3
    assert all(h["domain"] == "port" for h in T.search_terms("선", domain="port"))
    with pytest.raises(T.InputError):
        T.search_terms("선박", domain="health")
    t = T.get_term("https://w3id.org/ontocraft/terms/ship")
    assert t["ko"] == "선박" and t["source"]["license"] == "CC BY 4.0" and "seed" not in t
    with pytest.raises(T.InputError):
        T.get_term("no-such-term")


# MCP 서버

def _mcp():
    pytest.importorskip("mcp")
    from ontocraft_check.mcp_server import build_server
    return build_server()


def _call(server, name, args):
    res = asyncio.run(server.call_tool(name, args))
    assert not res.is_error, res
    return res.content[0].text


def test_mcp_lists_five_tools():
    server = _mcp()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"check_ontology", "explain_rule", "list_rules", "search_terms", "get_term"}
    assert "파일은 이 컴퓨터 밖으로 보내지 않습니다" in server.instructions
    assert "OWL 2 RL" in server.instructions


def test_mcp_call_tools():
    server = _mcp()
    s = json.loads(_call(server, "check_ontology", {"ontology": f("maritime-like.ttl"), "domains": ["maritime"]}))
    assert s["tool"] == "ontocraft-check" and s["registry_candidates"]["REG01"] >= 1
    md = _call(server, "check_ontology", {"ontology": Path(f("clean.ttl")).read_text(encoding="utf-8"),
                                          "format": "markdown", "use_registry": False})
    assert md.startswith(f"# {TOOL_TITLE} 보고서")
    assert json.loads(_call(server, "explain_rule", {"rule_id": "P13"}))["rule"] == "P13"
    assert len(json.loads(_call(server, "list_rules", {}))) == len(RULE_TITLES)
    hits = json.loads(_call(server, "search_terms", {"query": "선박", "limit": 2}))
    assert hits[0]["id"] == "ship" and len(hits) <= 2
    assert json.loads(_call(server, "get_term", {"id": "ship"}))["en"] == "ship"


def test_mcp_errors_are_tool_errors():
    server = _mcp()
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("get_term", {"id": "no-such-term"}))
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("check_ontology", {"ontology": "/nope/missing.ttl"}))


def test_mcp_missing_dependency_message(monkeypatch, capsys):
    import ontocraft_check.mcp_server as ms
    monkeypatch.setattr(ms, "MCPServer", None)
    assert ms.main() == 2
    assert "ontocraft-check[mcp]" in capsys.readouterr().err
