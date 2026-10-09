"""0.6.0에서 더한 CQ 커버리지(checks/cq.py, 정보 항목 CQ01)."""

import json

import pytest

from ontocraft_check import __version__
from ontocraft_check import tools as T
from ontocraft_check.checks.cq import (NOT_DELETE_NOTE, NOT_FIT_NOTE, CypherError, parse_cypher,
                                       screaming_snake)
from ontocraft_check.cli import main
from ontocraft_check.render import RULE_TITLES, render
from ontocraft_check.rules import rule_info
from ontocraft_check.runner import run

ONTO = """@prefix ex:   <https://example.org/cq#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
<https://example.org/cq> a owl:Ontology .
ex:PhysicalEntity a owl:Class ; rdfs:label "PhysicalEntity"@en .
ex:Vessel a owl:Class ; rdfs:subClassOf ex:PhysicalEntity ; rdfs:label "Vessel"@en .
ex:CargoShip a owl:Class ; rdfs:subClassOf ex:Vessel .
ex:Harbour a owl:Class ; rdfs:label "Port"@en .
ex:Berth a owl:Class .
ex:Unused a owl:Class .
ex:arrivedAt a owl:ObjectProperty ; rdfs:label "ARRIVED_AT"@en ; rdfs:domain ex:Vessel ; rdfs:range ex:Harbour .
ex:dockedAt a owl:ObjectProperty ; rdfs:domain ex:Vessel ; rdfs:range ex:Berth .
ex:hasBerth a owl:ObjectProperty ; rdfs:label "BERTH_OF"@en .
ex:neverUsed a owl:ObjectProperty ; rdfs:label "NEVER_USED"@en .
ex:Vessel_draft a owl:DatatypeProperty ; rdfs:label "draft"@en ; rdfs:domain ex:Vessel ; rdfs:range xsd:double .
ex:PhysicalEntity_name a owl:DatatypeProperty ; rdfs:label "name"@en ; rdfs:domain ex:PhysicalEntity .
ex:Harbour_unlocode a owl:DatatypeProperty ; rdfs:domain ex:Harbour .
ex:CargoShip_cargoType a owl:DatatypeProperty ; rdfs:label "cargoType"@en .
ex:Berth_draft a owl:DatatypeProperty ; rdfs:label "draft"@en ; rdfs:domain ex:Berth .
ex:Berth_unusedProp a owl:DatatypeProperty ; rdfs:domain ex:Berth .
"""


def cq_file(tmp_path, items, name="cq.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"total": len(items), "items": items}, ensure_ascii=False), encoding="utf-8")
    return str(p)


@pytest.fixture
def onto(tmp_path):
    p = tmp_path / "o.ttl"
    p.write_text(ONTO, encoding="utf-8")
    return str(p)


def by_id(report, cid):
    return next(r for r in report.cq["per_cq"] if r["id"] == cid)


def cq01(report):
    return {x.detail["name"]: x for x in report.findings if x.rule == "CQ01"}


def test_version_and_rule():
    assert __version__ == "0.7.1"
    assert "CQ01" in RULE_TITLES
    info = rule_info("cq01")
    assert info["category"] == "cq" and info["severity"] == "info"
    assert "CQ01" in {r["rule"] for r in T.list_rules()}


# Cypher 파서

def test_parser_multiple_relation_types_and_var_length():
    p = parse_cypher("MATCH (a:Vessel)-[r:ARRIVED_AT|:DOCKED_AT]->(b), (a)-[:BERTH_OF|NEXT*1..3]-(c:Berth) RETURN a.name, r.since")
    assert p["rel_types"] == ["ARRIVED_AT", "DOCKED_AT", "BERTH_OF", "NEXT"]
    assert p["labels"] == ["Vessel", "Berth"]
    assert ("r", "since") in p["rel_props"]
    assert ("a", frozenset({"Vessel"}), "name") in p["accesses"]


def test_parser_ignores_string_literals_and_comments():
    q = ("MATCH (v:Vessel {name:'(x:Fake)-[:FAKE]->(y)'}) // (z:Commented)\n"
         "WHERE v.flag = \"a.b [:NOPE]\" RETURN v.draft, 'w.ghost' AS s")
    p = parse_cypher(q)
    assert p["labels"] == ["Vessel"]
    assert p["rel_types"] == []
    props = {x[2] for x in p["accesses"]}
    assert props == {"name", "flag", "draft"}


def test_parser_unlabeled_variable_and_functions():
    p = parse_cypher("MATCH (x)-[:ARRIVED_AT]->(:Port) WHERE x.draft > 3 RETURN count(x), labels(x), x.name, $p.k")
    assert p["node_vars"]["x"] == []
    assert ("x", frozenset(), "draft") in p["accesses"]
    assert ("(익명1)" not in p["node_vars"]) or p["node_vars"]["(익명1)"] == ["Port"]
    assert all(x[2] != "k" for x in p["accesses"])  # $p.k 는 매개변수


def test_parser_label_predicate_and_backticks():
    p = parse_cypher("MATCH (v)-[:`ARRIVED_AT`]->(h) WHERE v:Vessel RETURN v.draft")
    assert "Vessel" in p["labels"] and p["rel_types"] == ["ARRIVED_AT"]
    assert ("v", frozenset({"Vessel"}), "draft") in p["accesses"]


def test_parser_failures():
    for bad in ("", "MATCH (v:Vessel RETURN v", "RETURN 1", "MATCH (v:Vessel {name:'x}) RETURN v"):
        with pytest.raises(CypherError):
            parse_cypher(bad)


def test_screaming_snake():
    assert screaming_snake("arrivedAt") == "ARRIVED_AT"
    assert screaming_snake("hasVTSZone") == "HAS_VTS_ZONE"
    assert screaming_snake("dockedAt") == "DOCKED_AT"


# 이름 맞추기 1~3

def test_name_matching_rules(onto, tmp_path):
    items = [
        {"id": "C1", "q": "입항", "cypher": "MATCH (v:Vessel)-[:ARRIVED_AT]->(p:Port {unlocode:'KRPUS'}) RETURN v.name, v.draft"},
        {"id": "C2", "q": "접안", "cypher": "MATCH (v:Vessel)-[:DOCKED_AT]->(b:Berth) RETURN b.draft"},
        {"id": "C3", "q": "모호", "cypher": "MATCH (x)-[:BERTH_OF]->(y) RETURN x.draft"},
        {"id": "C4", "q": "하위", "cypher": "MATCH (v:Vessel) RETURN v.cargoType, v.nothing"},
    ]
    r = run(onto, cq=cq_file(tmp_path, items))
    c1 = by_id(r, "C1")
    # 규칙 2: 로컬 이름(Vessel)과 @en 레이블(Port -> Harbour) 모두로 맞춥니다
    assert c1["classes"] == ["ex:Harbour", "ex:Vessel"]
    # 규칙 1: @en 레이블
    assert c1["object_properties"] == ["ex:arrivedAt"]
    # 규칙 3: v.name 은 조상 PhysicalEntity 에서, v.draft 는 Vessel 에서, {unlocode} 는 「클래스_속성」 이름에서
    assert set(c1["data_properties"]) == {"ex:PhysicalEntity_name", "ex:Vessel_draft", "ex:Harbour_unlocode"}
    # 규칙 1: @en 레이블이 없으면 로컬 이름을 SCREAMING_SNAKE 로
    assert by_id(r, "C2")["object_properties"] == ["ex:dockedAt"]
    assert by_id(r, "C2")["data_properties"] == ["ex:Berth_draft"]  # 같은 이름이라도 변수 라벨의 클래스 것만
    assert r.cq["relation_matched_by_snake"] == ["DOCKED_AT"]
    # 라벨 없는 변수: 후보 모두를 모호로 세고 「닿음」에 넣지 않습니다
    c3 = by_id(r, "C3")
    assert c3["data_properties"] == [] and c3["ambiguous"] == ["x.draft(2개 후보)"]
    dp = {e["short"]: e for e in r.cq["elements"] if e["kind"] == "data_property"}
    assert dp["ex:Vessel_draft"]["cq"] == ["C1"] and dp["ex:Vessel_draft"]["ambiguous_cq"] == ["C3"]
    # 하위 클래스에만 있는 속성은 CQ01 로 내고 참고를 붙입니다. 「클래스_속성」 이름만으로도 주인을 압니다
    miss = cq01(r)
    assert "Vessel.cargoType" in miss and "ex:CargoShip_cargoType" in miss["Vessel.cargoType"].message
    assert "Vessel.nothing" in miss
    cov = r.cq["coverage"]
    assert cov["class"]["total"] == 6 and cov["class"]["touched"] == 3
    assert cov["object_property"] == {"name": "관계(객체 속성)", "touched": 3, "total": 4, "ambiguous_only": 0}
    unreached = {k: [x["short"] for x in v] for k, v in r.cq["unreached"].items()}
    assert unreached["object_property"] == ["ex:neverUsed"]
    assert "ex:Berth_unusedProp" in unreached["data_property"] and "ex:Unused" in unreached["class"]
    assert all(x.severity == "info" for x in r.findings if x.rule == "CQ01")


def test_allow_lists_with_wildcard(onto, tmp_path):
    items = [{"id": "A1", "q": "허용", "cypher": "MATCH (k:KG_DevKG)-[:BROADER]->(c:Concept), (v:Vessel)-[:HAS_LEGAL_BASIS]->(z:Other) RETURN c.prefLabel"}]
    path = cq_file(tmp_path, items)
    r0 = run(onto, cq=path)
    assert set(cq01(r0)) == {"KG_DevKG", "Concept", "Other", "BROADER", "HAS_LEGAL_BASIS"}
    r1 = run(onto, cq=path, cq_allow_labels="KG_*,Concept", cq_allow_relations=["BROADER", "HAS_LEGAL_BASIS"])
    assert set(cq01(r1)) == {"Other"}
    assert by_id(r1, "A1")["allowed"] == ["BROADER", "Concept", "HAS_LEGAL_BASIS", "KG_DevKG"]
    assert r1.cq["allow_labels"] == ["KG_*", "Concept"]
    r2 = run(onto, cq=path, cq_allow_labels="KG_*,Concept,Other", cq_allow_relations="BROADER,HAS_LEGAL_BASIS",
             disable="CQ01")
    assert not cq01(r2)


def test_sparql_path_and_query_field(onto, tmp_path):
    items = [
        {"id": "S1", "q": "SPARQL", "sparql": "SELECT ?v ?d WHERE { ?v a ex:Vessel ; ex:arrivedAt ?h ; ex:Vessel_draft ?d . ?h ex:Ghost ?g }"},
        {"id": "S2", "q": "깨진 질의", "sparql": "SELECT ?v WHERE { ?v a nope:X "},
    ]
    r = run(onto, cq=cq_file(tmp_path, items))
    s1 = by_id(r, "S1")
    assert s1["lang"] == "sparql"
    assert s1["classes"] == ["ex:Vessel"] and s1["object_properties"] == ["ex:arrivedAt"]
    assert s1["data_properties"] == ["ex:Vessel_draft"]
    assert "ex:Ghost" in cq01(r)
    assert [x["id"] for x in r.cq["failed"]] == ["S2"] and "SPARQL" in r.cq["failed"][0]["reason"]
    # 질의 필드 이름을 바꿉니다
    items2 = [{"id": "Q1", "q": "다른 필드", "query": "MATCH (v:Vessel)-[:ARRIVED_AT]->(:Port) RETURN v.draft"},
              {"id": "Q2", "q": "다른 필드 SPARQL", "query": "PREFIX ex: <https://example.org/cq#> SELECT * WHERE { ?b a ex:Berth }"}]
    r2 = run(onto, cq=cq_file(tmp_path, items2, "cq2.json"), cq_query_field="query")
    assert by_id(r2, "Q1")["lang"] == "cypher" and by_id(r2, "Q2")["lang"] == "sparql"
    assert by_id(r2, "Q2")["classes"] == ["ex:Berth"]
    assert r2.cq["parsed"] == 2


def test_parse_failures_are_listed(onto, tmp_path):
    items = [{"id": "F1", "q": "깨짐", "cypher": "MATCH (v:Vessel RETURN v"},
             {"id": "F2", "q": "질의 없음"},
             {"id": "OK", "q": "정상", "cypher": "MATCH (v:Vessel) RETURN v.draft"}]
    r = run(onto, cq=cq_file(tmp_path, items))
    assert r.cq["total"] == 3 and r.cq["parsed"] == 1
    assert [x["id"] for x in r.cq["failed"]] == ["F1", "F2"]
    md = render(r, "md")
    assert "파싱하지 못한 CQ" in md and "F1" in md


# 보고서

def test_report_sentences_and_sections(onto, tmp_path):
    items = [{"id": "C1", "q": "입항", "cypher": "MATCH (v:Vessel)-[:ARRIVED_AT]->(p:Port) RETURN v.draft"}]
    r = run(onto, cq=cq_file(tmp_path, items))
    md = render(r, "md")
    assert NOT_DELETE_NOTE in md and NOT_FIT_NOTE in md
    assert "CQ가 닿지 않음은 지워도 된다는 뜻이 아닙니다" in md
    assert "질문이 업무에 맞는지는 판정하지 못합니다" in md
    # 「지워도 된다는 뜻이 아님」 문장은 닿지 않는 요소 목록 바로 위에 둡니다
    sec = md.split("CQ가 닿지 않는 요소", 1)[1]
    assert sec.lstrip().startswith(NOT_DELETE_NOTE)
    assert "## 8. CQ 커버리지" in md and "## 9. 이 보고서로 말할 수 없는 것" in md
    html = render(r, "html")
    assert "CQ가 닿지 않음은 지워도 된다는 뜻이 아닙니다" in html and "CQ 커버리지" in html
    j = json.loads(render(r, "json"))
    assert j["cq"]["coverage"]["object_property"]["touched"] == 1
    assert NOT_DELETE_NOTE in j["cq"]["notes"] and NOT_DELETE_NOTE in j["cannot_say"]
    assert j["summary"]["cq"]["status"] == "ran"


def test_big_tables_fold(onto, tmp_path):
    items = [{"id": f"C{i}", "q": "q", "cypher": "MATCH (v:Vessel) RETURN v.draft"} for i in range(15)]
    r = run(onto, cq=cq_file(tmp_path, items))
    md = render(r, "md")
    assert "<details><summary>CQ별 표 15행 보기</summary>" in md
    assert "<details><summary>CQ별 표 15행 보기</summary>" in render(r, "html")


def test_without_cq_report_unchanged(onto):
    r = run(onto)
    assert r.cq is None and "cq" not in r.ran
    md = render(r, "md")
    assert "CQ 커버리지" not in md and "## 8. 이 보고서로 말할 수 없는 것" in md
    j = json.loads(render(r, "json"))
    assert "cq" not in j and "cq" not in j["summary"]
    assert "CQ 커버리지" not in T.summarize(r)["by_category"]


def test_cli_and_tools(onto, tmp_path, capsys):
    items = [{"id": "C1", "q": "입항", "cypher": "MATCH (v:Vessel)-[:ARRIVED_AT]->(p:Port) RETURN v.draft"}]
    path = cq_file(tmp_path, items)
    out = tmp_path / "r.json"
    rc = main([onto, "--cq", path, "--cq-allow-labels", "KG_*", "--cq-allow-relations", "BROADER",
               "--format", "json", "--out", str(out)])
    assert rc == 0
    j = json.loads(out.read_text(encoding="utf-8"))
    assert j["cq"]["allow_labels"] == ["KG_*"] and j["cq"]["allow_relations"] == ["BROADER"]
    assert main([onto, "--cq", str(tmp_path / "없음.json")]) == 2
    md_file = tmp_path / "cq.md"
    md_file.write_text("| id | q |\n|---|---|\n", encoding="utf-8")
    assert main([onto, "--cq", str(md_file)]) == 2  # 마크다운 표는 읽지 않습니다
    s = T.check_ontology(onto, cq=json.dumps({"items": items}), use_registry=False)
    assert s["cq_coverage"]["coverage"]["data_property"]["touched"] == 1
    assert NOT_DELETE_NOTE in s["cq_coverage"]["notes"]
    s2 = T.check_ontology(onto, cq=path, cq_allow_labels=["Port"], use_registry=False, format="json")
    assert s2["cq"]["source"] == path


def test_worker_passes_cq_only_when_given():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    worker = (root / "web" / "ontocraft-check-worker.js").read_text(encoding="utf-8")
    assert '("cq", "cq_query_field", "cq_allow_labels", "cq_allow_relations")' in worker
    assert '("domains", "disable", "group_over", "strict_domains")' in worker
    demo = (root / "web" / "demo.html").read_text(encoding="utf-8")
    assert "...(cq ? { cq } : {})" in demo


def test_mcp_check_ontology_has_cq_args():
    pytest.importorskip("mcp")
    import asyncio

    from ontocraft_check.mcp_server import build_server
    tools = {t.name: t for t in asyncio.run(build_server().list_tools())}
    props = tools["check_ontology"].input_schema["properties"]
    assert {"cq", "cq_query_field", "cq_allow_labels", "cq_allow_relations"} <= set(props)


# ---------------------------------------------------------------- 0.6.0 다듬기: 후보 1개, labels() 목록


def test_unique_candidate_not_counted_as_touched(onto, tmp_path):
    items = [
        {"id": "U1", "q": "후보 하나", "cypher": "MATCH (n) WHERE n.unlocode IS NOT NULL RETURN n.unlocode"},
        {"id": "U2", "q": "후보 둘", "cypher": "MATCH (x)-[:BERTH_OF]->(y) RETURN x.draft"},
    ]
    r = run(onto, cq=cq_file(tmp_path, items))
    u1 = by_id(r, "U1")
    assert u1["ambiguous"] == ["n.unlocode(후보 1개: ex:Harbour_unlocode)"]
    assert u1["unique_candidate"] == [{"access": "n.unlocode", "property": "ex:Harbour_unlocode"}]
    assert u1["data_properties"] == []
    assert by_id(r, "U2")["unique_candidate"] == []
    amb = r.cq["ambiguous_accesses"]
    assert amb["total"] == 2 and amb["unique_candidate"] == 1
    assert amb["unique_candidate_items"] == [{"cq": "U1", "access": "n.unlocode", "property": "ex:Harbour_unlocode"}]
    # 「닿음」에는 넣지 않습니다
    assert r.cq["coverage"]["data_property"]["touched"] == 0
    md = render(r, "md")
    assert "2개 가운데 후보가 하나뿐인 것 1개" in md
    assert "「닿음」에 넣지 않았습니다" in md
    summary = json.loads(render(r, "json"))["cq"]["ambiguous_accesses"]
    assert summary["unique_candidate"] == 1


def test_labels_list_any_in(onto, tmp_path):
    items = [{"id": "L1", "q": "목록",
              "cypher": "MATCH (n) WHERE any(l IN labels(n) WHERE l IN ['Vessel','Port','Ghost']) RETURN n.draft"}]
    r = run(onto, cq=cq_file(tmp_path, items))
    row = by_id(r, "L1")
    assert row["classes"] == ["ex:Harbour", "ex:Vessel"]
    assert row["labels_from_list"] == ["n:Vessel", "n:Port", "n:Ghost"]
    assert row["data_properties"] == ["ex:Vessel_draft"] and row["ambiguous"] == []
    f = cq01(r)["Ghost"]
    assert "labels() 목록에서 읽음" in f.message
    md = render(r, "md")
    assert "labels() 목록에서 읽음 n:Vessel" in md


def test_labels_list_literal_in_and_equals(onto, tmp_path):
    items = [
        {"id": "L2", "q": "리터럴", "cypher": "MATCH (n) WHERE 'Berth' IN labels(n) RETURN count(n)"},
        {"id": "L3", "q": "같음", "cypher": "MATCH (n) WHERE any(l IN labels(n) WHERE l = 'Vessel') RETURN n"},
        {"id": "L4", "q": "목록 식", "cypher": "MATCH (n) UNWIND [l IN labels(n) WHERE l IN ['Berth']] AS t RETURN t"},
    ]
    r = run(onto, cq=cq_file(tmp_path, items))
    assert by_id(r, "L2")["classes"] == ["ex:Berth"]
    assert by_id(r, "L3")["classes"] == ["ex:Vessel"]
    assert by_id(r, "L4")["classes"] == ["ex:Berth"]
    assert [x["cq"] for x in r.cq["labels_from_list"]] == ["L2", "L3", "L4"]
    assert r.cq["no_touch"] == []


def test_labels_list_negations_ignored():
    for q in ["MATCH (n) RETURN [l IN labels(n) WHERE NOT l IN ['Vessel']][-1]",
              "MATCH (n) WHERE none(l IN labels(n) WHERE l IN ['Vessel']) RETURN n",
              "MATCH (n) WHERE NOT any(l IN labels(n) WHERE l = 'Vessel') RETURN n",
              "MATCH (n) WHERE NOT 'Vessel' IN labels(n) RETURN n"]:
        p = parse_cypher(q)
        assert p["labels_from_list"] == {} and p["labels"] == [], q


def test_labels_list_only_known_node_vars():
    p = parse_cypher("MATCH (n:Vessel) WITH collect(n) AS ns UNWIND ns AS m "
                     "WHERE 'Port' IN labels(m) RETURN m")
    assert p["labels_from_list"] == {}
    p2 = parse_cypher("MATCH (n:Vessel) WHERE 'Port' IN labels(n) RETURN n")
    assert p2["labels_from_list"] == {"n": ["Port"]} and p2["node_vars"]["n"] == ["Port", "Vessel"]
