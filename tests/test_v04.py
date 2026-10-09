"""0.4.0에서 더한 기능: 관련 분야 함께 보기(--strict-domains), 속성과 개념 용어(REG03), 용어 kind 분기."""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from helpers import f, local, run
from ontocraft_check import __version__
from ontocraft_check import tools as T
from ontocraft_check.checks.registry import builtin_manifest, expand_domains, related_map
from ontocraft_check.cli import main
from ontocraft_check.related import default_related
from ontocraft_check.render import RULE_TITLES, render

ROOT = Path(__file__).resolve().parents[1]
PORT_TERMS = {"Anchorage", "Berth", "DangerousGoods", "Loading", "Discharging", "PortFacility", "CargoHandling"}
PROPS = {"commandedBy", "arrivedAt", "arrivalTime"}


def by_rule(report, rule):
    return {local(x.target) for x in report.findings if x.rule == rule}


def test_version():
    assert __version__.startswith("0.")


# 관련 분야

def test_default_related_table_is_symmetric_and_excludes_weak_pairs():
    rel = default_related()
    assert rel["maritime"] == ["defense", "port"]
    assert rel["port"] == ["maritime"]
    assert rel["mfg-ai"] == ["maint", "physical-ai", "semiconductor"]
    assert "smartcity" not in rel and "port" not in rel.get("smartcity", [])
    for a, bs in rel.items():
        for b in bs:
            assert a in rel[b]


def test_builtin_manifest_has_related():
    doms = {d["id"]: d for d in builtin_manifest()["domains"]}
    assert all("related" in d for d in doms.values())
    assert doms["maritime"]["related"] == ["defense", "port"]
    assert doms["smartcity"]["related"] == []
    rel, src = related_map(ROOT / "src" / "ontocraft_check" / "data" / "registry")
    assert src == "manifest.json" and rel["maritime"] == ["defense", "port"]


def test_maritime_brings_port_terms_as_reg01():
    r = run(f("port-terms.ttl"), registry_dir="builtin", domains=["maritime"])
    assert r.options["domains"] == ["maritime"]
    assert r.options["related_domains"] == ["defense", "port"]
    assert r.options["strict_domains"] is False
    assert PORT_TERMS <= by_rule(r, "REG01")
    assert not PORT_TERMS & by_rule(r, "REG02")
    port = [x for x in r.findings if x.rule == "REG01" and x.detail["domain"] == "port"]
    assert port and all(x.detail.get("via_related") for x in port)
    assert not any(x.detail.get("via_related") for x in r.findings if x.rule == "REG01" and x.detail["domain"] == "maritime")
    md = render(r, "md")
    assert "관련 분야로 함께 봄: defense, port." in md
    assert "| 관련 분야로 함께 봄 | defense, port |" in md
    assert "--strict-domains" in md
    d = json.loads(render(r, "json"))
    assert d["options"]["related_domains"] == ["defense", "port"] and d["options"]["strict_domains"] is False


def test_strict_domains_keeps_only_chosen():
    r = run(f("port-terms.ttl"), registry_dir="builtin", domains=["maritime"], strict_domains=True)
    assert r.options["related_domains"] == [] and r.options["strict_domains"] is True
    assert PORT_TERMS <= by_rule(r, "REG02")
    assert not PORT_TERMS & by_rule(r, "REG01")
    md = render(r, "md")
    assert "관련 분야로 함께 봄:" not in md
    assert "| 관련 분야로 함께 봄 | (더하지 않음, --strict-domains) |" in md


def test_explicit_maritime_port_same_as_expanded():
    a = run(f("port-terms.ttl"), registry_dir="builtin", domains="maritime,port", strict_domains=True)
    assert PORT_TERMS <= by_rule(a, "REG01")


def test_no_domains_means_no_expansion():
    r = run(f("port-terms.ttl"), registry_dir="builtin")
    assert r.options["related_domains"] == []
    assert "관련 분야로 함께 봄" not in render(r, "md")


def test_folder_without_related_uses_default_table_within_known_domains():
    reg = f("registry-multi")
    rel, src = related_map(reg)
    assert src == "기본표"
    # registry-multi 에는 defense 가 없으므로 port 만 더합니다.
    assert expand_domains(reg, ["maritime"]) == ["port"]
    assert expand_domains(reg, ["maritime"], strict=True) == []
    assert expand_domains(reg, ["smartcity"]) == []


def test_folder_domains_json_related_overrides_default(tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    for did, ko in (("maritime", "선박"), ("port", "선석"), ("smartcity", "센서")):
        (reg / f"{did}.json").write_text(json.dumps({"domain": {"id": did}, "terms": [{"id": f"{did}-x", "ko": ko}]}),
                                         encoding="utf-8")
    (reg / "domains.json").write_text(json.dumps({"domains": [
        {"id": "maritime", "related": ["smartcity"]}, {"id": "port"}, {"id": "smartcity"}]}), encoding="utf-8")
    rel, src = related_map(reg)
    assert src == "domains.json" and rel == {"maritime": ["smartcity"], "smartcity": ["maritime"]}
    assert expand_domains(reg, ["maritime"]) == ["smartcity"]


def test_unknown_domain_does_not_expand():
    r = run(f("port-terms.ttl"), registry_dir="builtin", domains=["nope"])
    assert r.options["related_domains"] == []
    assert r.stats["registry_unknown_domains"] == ["nope"]


def test_cli_strict_domains(tmp_path):
    out = tmp_path / "r.json"
    main([f("port-terms.ttl"), "--registry", "builtin", "--domains", "maritime", "--format", "json", "--out", str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["options"]["related_domains"] == ["defense", "port"]
    main([f("port-terms.ttl"), "--registry", "builtin", "--domains", "maritime", "--strict-domains",
          "--format", "json", "--out", str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["options"]["related_domains"] == [] and d["options"]["strict_domains"] is True


# 속성과 개념 용어(REG03)

def test_properties_go_to_reg03_not_reg01():
    r = run(f("port-terms.ttl"), registry_dir="builtin", domains=["maritime"])
    assert not PROPS & by_rule(r, "REG01")
    assert not PROPS & by_rule(r, "REG02")
    assert PROPS == by_rule(r, "REG03")
    reg03 = {(local(x.target), x.detail["term_id"]) for x in r.findings if x.rule == "REG03"}
    assert ("commandedBy", "ship-master") in reg03 and ("arrivedAt", "port-call") in reg03
    msgs = {local(x.target): x.message for x in r.findings if x.rule == "REG03"}
    assert "개념 용어 「기항」과 표기가 같습니다(https://w3id.org/ontocraft/terms/port-call)" in msgs["arrivedAt"]
    assert "개념 용어 「선장」과 표기가 같습니다" in msgs["commandedBy"]
    for x in r.findings:
        if x.rule == "REG03":
            assert x.severity == "info"
            assert "관계 이름은 동사구로, 개념과의 연결은 range 클래스에서 하기를 권합니다." in x.message
            assert x.detail["entity_kind"] in ("객체 속성", "데이터 속성")
    assert {x.detail["entity_kind"] for x in r.findings if x.rule == "REG03" and local(x.target) == "arrivalTime"} == {"데이터 속성"}
    md = render(r, "md")
    assert "### REG03 속성 이름이 개념 용어와 같음 (정보, 3건)" in md
    assert all(x.severity == "info" for x in r.by_category("registry"))


def test_reg03_respects_domains():
    # 입항은 port 용어라 strict maritime 에서는 REG03 도 내지 않습니다. 선장은 maritime 이라 남습니다.
    r = run(f("port-terms.ttl"), registry_dir="builtin", domains=["maritime"], strict_domains=True)
    assert by_rule(r, "REG03") == {"commandedBy"}


def test_reg03_rule_info_and_summary():
    info = T.explain_rule("REG03")
    assert info["title"] == "속성 이름이 개념 용어와 같음" and info["severity"] == "info"
    assert "REG03" in {x["rule"] for x in T.list_rules()}
    assert "REG03" in RULE_TITLES
    s = T.check_ontology(f("port-terms.ttl"), domains=["maritime"])
    assert s["registry_candidates"]["REG03"] == 3
    assert s["related_domains"] == ["defense", "port"]
    s = T.check_ontology(f("port-terms.ttl"), domains=["maritime"], strict_domains=True)
    assert "related_domains" not in s and s["registry_candidates"]["REG02"] >= 7


# 용어 kind 분기(지금 데이터에는 없음)

@pytest.fixture
def kind_registry(tmp_path):
    reg = tmp_path / "kinds"
    reg.mkdir()
    (reg / "k.json").write_text(json.dumps({"domain": {"id": "k", "name": "종류 시험"}, "terms": [
        {"id": "rel-command", "ko": "지휘함", "kind": "relation"},
        {"id": "prop-arrival", "ko": "입항 시각", "kind": "property"},
        {"id": "cls-master", "ko": "선장", "kind": "class"},
        {"id": "concept-berth", "ko": "선석"},
        {"id": "rel-berth", "ko": "접안함", "kind": "relation"},
        {"id": "weird", "ko": "정박", "kind": "nonsense"},
    ]}, ensure_ascii=False), encoding="utf-8")
    onto = tmp_path / "o.ttl"
    onto.write_text(
        "@prefix ex: <https://example.org/k#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "ex:commands a owl:ObjectProperty ; rdfs:label \"지휘함\"@ko .\n"
        "ex:arrivalTime a owl:DatatypeProperty ; rdfs:label \"입항 시각\"@ko .\n"
        "ex:master a owl:ObjectProperty ; rdfs:label \"선장\"@ko .\n"
        "ex:Master a owl:Class ; rdfs:label \"선장\"@ko .\n"
        "ex:Berth a owl:Class ; rdfs:label \"선석\"@ko .\n"
        "ex:Docking a owl:Class ; rdfs:label \"접안함\"@ko .\n"
        "ex:Anchoring a owl:Class ; rdfs:label \"정박\"@ko .\n", encoding="utf-8")
    return str(onto), str(reg)


def test_kind_same_kind_matches(kind_registry):
    onto, reg = kind_registry
    r = run(onto, registry_dir=reg)
    reg01 = {(local(x.target), x.detail["term_id"]) for x in r.findings if x.rule == "REG01"}
    assert reg01 == {
        ("commands", "rel-command"),      # 속성과 relation 용어
        ("arrivalTime", "prop-arrival"),  # 속성과 property 용어
        ("Master", "cls-master"),         # 클래스와 class 용어
        ("Berth", "concept-berth"),       # 클래스와 kind 없는 개념 용어
        ("Anchoring", "weird"),           # 모르는 kind 는 없는 것으로 봅니다
    }
    kinds = {x.detail["term_id"]: x.detail.get("term_kind") for x in r.findings if x.rule == "REG01"}
    assert kinds["rel-command"] == "relation" and kinds["concept-berth"] is None
    # 속성과 class 용어는 REG03, 클래스와 relation 용어(접안함)는 맞추지 않습니다.
    assert {(local(x.target), x.detail["term_id"]) for x in r.findings if x.rule == "REG03"} == {("master", "cls-master")}
    assert "Docking" not in {local(x.target) for x in r.by_category("registry")}
    assert r.stats["registry_kind_skipped"] == 1


def test_sync_registry_keeps_kind_and_related(tmp_path):
    spec = importlib.util.spec_from_file_location("sync_registry", ROOT / "scripts" / "sync_registry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reg = tmp_path / "aki" / "data" / "registry"
    reg.mkdir(parents=True)
    doms = [{"id": "maritime", "status": "published", "order": 1},
            {"id": "port", "status": "published", "order": 2},
            {"id": "defense", "status": "draft", "order": 3}]
    (reg / "domains.json").write_text(json.dumps({"domains": doms}), encoding="utf-8")
    for d in doms:
        (reg / f"{d['id']}.json").write_text(json.dumps({"domain": {"id": d["id"]}, "terms": [
            {"id": f"{d['id']}-a", "ko": "가", "definition": "뜻", "kind": "relation"}]}), encoding="utf-8")
    out = tmp_path / "out"
    m = mod.build(tmp_path / "aki", "2026-01-01", out)
    rel = {d["id"]: d["related"] for d in m["domains"]}
    assert rel == {"maritime": ["port"], "port": ["maritime"]}  # 공개하지 않은 defense 는 뺍니다
    assert m["related_source"].startswith("기본표")
    t = json.loads((out / "maritime.json").read_text(encoding="utf-8"))["terms"][0]
    assert t["kind"] == "relation"
    # domains.json 에 related 가 있으면 그것을 씁니다(한쪽에만 적어도 양방향).
    doms[0]["related"] = []
    doms[1]["related"] = []
    (reg / "domains.json").write_text(json.dumps({"domains": doms}), encoding="utf-8")
    m = mod.build(tmp_path / "aki", "2026-01-01", out)
    assert m["related_source"] == "domains.json"
    assert {d["id"]: d["related"] for d in m["domains"]} == {"maritime": [], "port": []}


# 브라우저 실행기와 MCP

def test_worker_passes_strict_domains_only_when_true():
    worker = (ROOT / "web" / "ontocraft-check-worker.js").read_text(encoding="utf-8")
    assert "strict_domains" in worker
    assert "m.strict_domains === true ? true : null" in worker
    assert '("domains", "disable", "group_over", "strict_domains")' in worker
    assert f"ontocraft_check-{__version__}-py3-none-any.whl" in (ROOT / "web" / "demo.html").read_text(encoding="utf-8")


def test_mcp_check_ontology_strict_domains():
    pytest.importorskip("mcp")
    from ontocraft_check.mcp_server import build_server
    server = build_server()
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "strict_domains" in tools["check_ontology"].input_schema["properties"]
    res = asyncio.run(server.call_tool("check_ontology", {"ontology": f("port-terms.ttl"), "domains": ["maritime"],
                                                          "strict_domains": True}))
    s = json.loads(res.content[0].text)
    assert "related_domains" not in s and s["registry_candidates"]["REG02"] >= 7
