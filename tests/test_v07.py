"""0.7.2: 등록부 영어 대조와 @ko 0개 구분, --ignore-names, ONTOFLOW CQ 형식·프로필."""

import asyncio
import json

import pytest

from ontocraft_check import __version__
from ontocraft_check import tools as T
from ontocraft_check.checks.cq import iri_segment, load_cq, load_cq_doc, parse_cypher
from ontocraft_check.cli import main
from ontocraft_check.graph import split_name
from ontocraft_check.render import render
from ontocraft_check.rules import rule_info
from ontocraft_check.runner import run

from helpers import FIX, f

DEMO = "https://ontocraft.com/ontology/demo/"
ONTO = f("ontoflow-like.ttl")
CQ = f("ontoflow-cq.json")
BASE = "https://ontocraft.com/ontology/{project}/"


def short(x):
    return x.replace(DEMO, "")


def test_version():
    assert __version__ == "0.7.2"


# 1. 등록부: @ko 0개 구분과 영어 대조


def test_no_ko_labels_reported_as_reason_not_as_no_match():
    r = run(ONTO, registry_dir="builtin")
    assert r.stats["registry_ko_labels"] == 0 and r.stats["registry_no_ko"] is True
    sk = [k for k in r.skipped if k.category == "registry"]
    assert sk and "대조할 한국어 표기가 없습니다(@ko 레이블 0개)" in sk[0].reason
    md = render(r, "md")
    assert "실행(@ko 레이블 0개, 한국어 표기 대조 불가)" in md
    assert "등록부에 맞는 용어가 없다는 뜻이 아닙니다" in md
    j = json.loads(render(r, "json"))
    assert j["summary"]["registry"]["note"].startswith("실행(@ko 레이블 0개")


def test_english_match_is_low_confidence_and_marked():
    r = run(ONTO, registry_dir="builtin")
    reg = {short(x.target): x for x in r.findings if x.rule == "REG01"}
    assert {"Ship", "Voyage", "BulkCargo"} <= set(reg)
    for x in reg.values():
        assert x.detail["match_lang"] == "en" and x.detail["confidence"] == "낮음"
        assert "영어 이름으로 맞춤" in x.message
    assert reg["Ship"].detail["term_id"] == "ship"
    # 언어 태그 없는 레이블 "Cargo lot" 은 맞지 않고, 로컬 이름 BulkCargo 를 띄어 쓴 bulk cargo 가 맞습니다.
    assert reg["BulkCargo"].detail["matched_source"] == "로컬 이름"
    assert reg["BulkCargo"].detail["term_id"] == "bulk-cargo"
    # 속성은 영어로 REG03 을 내지 않습니다.
    assert not [x for x in r.findings if x.rule == "REG03"]
    assert r.stats["registry_reg01_by_lang"]["en"] == len(reg)


def test_registry_match_modes():
    ko = run(ONTO, registry_dir="builtin", registry_match="ko")
    assert not [x for x in ko.findings if x.category == "registry"]
    assert any("영어 이름 대조를 하려면" in k.reason for k in ko.skipped)
    en = run(ONTO, registry_dir="builtin", registry_match="en")
    assert en.stats["registry_ko_labels"] == 0 and not en.stats.get("registry_no_ko")
    assert {x.target for x in en.findings if x.rule == "REG01"} == \
        {x.target for x in run(ONTO, registry_dir="builtin").findings if x.rule == "REG01"}
    with pytest.raises(Exception):
        run(ONTO, registry_dir="builtin", registry_match="jp")


KO_FIRST = """@prefix ex: <https://example.org/k#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://example.org/k> a owl:Ontology .
ex:Voyage a owl:Class ; rdfs:label "항차"@ko , "Voyage"@en .
ex:Ship a owl:Class ; rdfs:label "시험용 본선"@ko , "Ship"@en .
"""


def test_korean_first_then_english(tmp_path):
    p = tmp_path / "k.ttl"
    p.write_text(KO_FIRST, encoding="utf-8")
    r = run(str(p), registry_dir="builtin")
    reg = {x.target.split("#")[-1]: x for x in r.findings if x.rule == "REG01"}
    # 항차는 한국어 표제어로 맞았으니 영어로 다시 맞추지 않습니다. 「시험용 본선」은 한국어로 맞지 않아 영어 Ship 으로 맞춥니다.
    assert reg["Voyage"].detail["confidence"] == "높음" and "match_lang" not in reg["Voyage"].detail
    assert reg["Ship"].detail["match_lang"] == "en"
    assert not [k for k in r.skipped if k.category == "registry"]


def test_split_name():
    assert split_name("ChemicalAccident") == "Chemical Accident"
    assert split_name("ship_type") == "ship type"
    assert split_name("HTTPServer") == "HTTP Server"


# 2. --ignore-names


def test_ignore_names_removes_naming_rules_only():
    before = run(ONTO)
    after = run(ONTO, ignore_names="ActionLog_*")
    p22 = lambda r: [short(x.target) for x in r.findings if x.rule == "P22"]  # noqa: E731
    p08 = lambda r: {short(x.target) for x in r.findings if x.rule == "P08"}  # noqa: E731
    assert p22(before) == ["ActionLog_fix_ship_name"] and p22(after) == []
    # 상대 경로(ActionLog_fix_ship_name/status)도 패턴에 맞아 그 클래스의 속성까지 빠집니다.
    assert {"ActionLog_fix_ship_name/status", "ActionLog_fix_ship_name/executedAt"} <= p08(before)
    assert not {x for x in p08(after) if x.startswith("ActionLog")}
    opt = after.options["ignore_names"]
    assert opt == [{"pattern": "ActionLog_*", "count": 3, "classes": 1, "properties": 2}]
    # 명명·메타데이터가 아닌 규칙(P13, P11 등)에는 쓰지 않습니다.
    p13 = lambda r: {short(x.target) for x in r.findings if x.rule == "P13"}  # noqa: E731
    assert p13(before) == p13(after) and "rel/LoggedEdit_fix_ship_name_Ship" in p13(after)
    meta = lambda r: [x.detail["count"] for x in r.findings if x.rule == "META02"]  # noqa: E731
    assert meta(before)[0] - meta(after)[0] == 3


def test_ignore_names_header_and_relative_path():
    r = run(ONTO, ignore_names=["ActionLog_*", "rel/LoggedEdit_*", "NoSuch*"])
    md = render(r, "md")
    assert "건너뛴 이름 패턴과 건수: ActionLog_*(요소 3개: 클래스 1, 속성 2), rel/LoggedEdit_*(요소 1개: 클래스 0, 속성 1), " \
           "NoSuch*(요소 0개: 클래스 0, 속성 0)" in md
    assert "모두 4개 요소를 명명·메타데이터 규칙(P08, P22, P32, LBL01, LBL02, META02, META03, META04)에서 뺐습니다" in md
    assert "| 건너뛴 이름 패턴 |" in md
    assert "이름 패턴(--ignore-names)으로 뺀 요소는" in md
    assert "건너뛴 이름 패턴" not in render(run(ONTO), "md")


# 3. ONTOFLOW CQ 형식


def test_ontoflow_format_autodetected():
    items, field, meta = load_cq_doc(CQ)
    assert meta["format"] == "ontoflow" and meta["name"].startswith("시험용")
    by = {x["id"]: x for x in items}
    assert by["D-1"]["lang"] == "cypher" and "MATCH" in by["D-1"]["query"] and by["D-1"]["q"].startswith("유조선")
    assert by["D-5"]["lang"] == "structured" and by["D-10"]["lang"] == "manual" and by["D-11"]["lang"] == "unknown"
    assert field.startswith("check.cypher")
    # 0.6 의 load_cq 는 기본 형식으로 읽습니다(호환).
    assert load_cq(CQ)[0][0]["query"] == ""
    assert load_cq_doc(CQ, cq_format="default")[2]["format"] == "default"


def test_ontoflow_parse_object_types():
    q = ("MATCH (m:Object {projectId:'p', objectType:'A'})-[:R]->(:Object {objectType:'B', code:'X'}) "
         "MATCH (o:Object) WHERE o.objectType IN ['C','D'] AND NOT o.objectType = 'E' "
         "AND type(r) = 'S' RETURN m.k, o.objectType, o.projectId")
    p = parse_cypher(q, profile="ontoflow")
    assert p["node_vars"]["m"] == ["A"] and p["node_vars"]["o"] == ["C", "D"]
    assert "Object" not in p["labels"] and p["infra_labels"] == ["Object"]
    assert set(p["rel_types"]) == {"R", "S"} and p["projects"] == ["p"]
    acc = {(v, prop) for v, _, prop in p["accesses"]}
    assert ("m", "k") in acc and ("(익명1)", "code") in acc
    assert not {prop for _, _, prop in p["accesses"]} & {"objectType", "projectId"}
    # 기본 프로필은 0.6 과 같습니다.
    d = parse_cypher(q)
    assert "Object" in d["labels"] and "infra_labels" not in d or d["infra_labels"] == []


def test_ontoflow_profile_coverage():
    r = run(ONTO, cq=CQ, cq_profile="ontoflow", cq_base=BASE)
    cq = r.cq
    assert cq["format"] == "ontoflow" and cq["profile"] == "ontoflow"
    cov = {k: (v["touched"], v["total"]) for k, v in cq["coverage"].items()}
    assert cov == {"class": (5, 7), "object_property": (3, 4), "data_property": (4, 8)}
    rows = {x["id"]: x for x in cq["per_cq"]}
    assert [short(x) for x in rows["D-1"]["classes"]] == ["Harbor", "Tanker", "Voyage"]
    assert [short(x) for x in rows["D-1"]["data_properties"]] == ["Harbor/unlocode"]
    assert [short(x) for x in rows["D-2"]["data_properties"]] == ["Ship/imo"]
    assert rows["D-3"]["object_properties"] == [] and "D-3" in cq["no_touch"]
    assert "https://ontocraft.com/ontology/shared/Company" in rows["D-4"]["classes"]
    assert [short(x) for x in rows["D-8"]["data_properties"]] == ["Ship/name"]  # 부모 클래스에서 물려받은 속성
    assert [short(x) for x in rows["D-7"]["object_properties"]] == ["rel/CALLED_AT"]
    assert cq["manual"] == [{"id": "D-10", "q": "화면에서 사람이 판정하는 질문"}]
    assert [x["id"] for x in cq["failed"]] == ["D-11"]
    # label-exists 처럼 projectId 가 없는 판정은 온톨로지 IRI 를 기준으로 씁니다.
    assert cq["bases"] == {"demo": DEMO, "(projectId 없음)": DEMO}
    assert cq["iri_rule"]["ok"] is True
    misses = {(x["kind"], x["name"]) for x in cq["unresolved"]}
    assert misses == {("property", "Tanker.draft"), ("label", "Berth")}
    md = render(r, "md")
    assert "이름 맞추기는 ONTOFLOW 프로필입니다" in md and "| 수동 판정(check 없음) | 1 |" in md
    assert "| ONTOFLOW IRI 규칙과 맞는 요소 | 클래스 7/7, 관계 4/4, 데이터 속성 8/8 |" in md


def test_ontoflow_base_defaults_to_template_when_ontology_iri_matches():
    a = run(ONTO, cq=CQ, cq_profile="ontoflow").cq
    b = run(ONTO, cq=CQ, cq_profile="ontoflow", cq_base=BASE).cq
    assert a["coverage"] == b["coverage"] and a["base_template"] == BASE


def test_ontoflow_catalog_with_default_profile_gives_hint():
    cq = run(ONTO, cq=CQ).cq
    assert cq["format"] == "ontoflow" and cq["profile"] == "default"
    assert "--cq-profile ontoflow" in cq["profile_hint"]
    assert ("label", "Object") in {(x["kind"], x["name"]) for x in cq["unresolved"]}


def test_iri_rule_mismatch_reported(tmp_path):
    p = tmp_path / "x.ttl"
    p.write_text("""@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://example.org/x/> a owl:Ontology .
<https://example.org/x/Ship> a owl:Class .
<https://example.org/x/hasName> a owl:DatatypeProperty .
<https://example.org/x/sailed> a owl:ObjectProperty .
""", encoding="utf-8")
    r = run(str(p), cq=CQ, cq_profile="ontoflow")
    rule = r.cq["iri_rule"]
    assert rule["ok"] is False
    assert rule["mismatch"]["data_property"] == ["https://example.org/x/hasName"]
    assert rule["mismatch"]["object_property"] == ["https://example.org/x/sailed"]
    assert "ONTOFLOW IRI 규칙" in render(r, "md")


def test_iri_segment_matches_exporter():
    assert iri_segment("a b/c#d?e%") == "a%20b%2Fc%23d%3Fe%25"
    assert iri_segment("선박") == "선박"


def test_bad_profile_rejected():
    from ontocraft_check.graph import LoadError
    with pytest.raises(LoadError):
        run(ONTO, cq=CQ, cq_profile="neo4j")
    with pytest.raises(LoadError):
        run(ONTO, cq=CQ, cq_format="csv")


# 4. 진입점


def test_cli_new_options(tmp_path, capsys):
    out = tmp_path / "r.json"
    code = main([ONTO, "--registry", "builtin", "--registry-match", "both", "--ignore-names", "ActionLog_*",
                 "--cq", CQ, "--cq-format", "ontoflow", "--cq-profile", "ontoflow", "--cq-base", BASE,
                 "--format", "json", "--out", str(out), "--fail-on", "none"])
    assert code == 0
    j = json.loads(out.read_text(encoding="utf-8"))
    assert j["options"]["ignore_names"][0]["count"] == 3 and j["options"]["registry_match"] == "both"
    assert j["cq"]["coverage"]["class"]["touched"] == 5


def test_tools_summary_new_fields():
    s = T.check_ontology(ONTO, cq=CQ, cq_profile="ontoflow", ignore_names=["ActionLog_*"])
    assert s["ignored_names"]["total"] == 3
    assert s["registry_note"].startswith("대조할 한국어 표기가 없습니다")
    assert s["registry_candidates"]["REG01_by_english_name"] >= 3
    assert s["cq_coverage"]["profile"] == "ontoflow" and s["cq_coverage"]["manual"] == ["D-10"]
    assert s["cq_coverage"]["iri_rule"]["ok"] is True


def test_mcp_has_new_arguments():
    pytest.importorskip("mcp")
    from ontocraft_check.mcp_server import build_server
    tools = {t.name: t for t in asyncio.run(build_server().list_tools())}
    props = tools["check_ontology"].input_schema["properties"]
    for k in ("ignore_names", "registry_match", "cq_format", "cq_profile", "cq_base"):
        assert k in props


def test_worker_passes_new_fields_only_when_given():
    worker = (FIX.parent.parent / "web" / "ontocraft-check-worker.js").read_text(encoding="utf-8")
    assert '("ignore_names", "registry_match", "cq_format", "cq_profile", "cq_base")' in worker
    demo = (FIX.parent.parent / "web" / "demo.html").read_text(encoding="utf-8")
    assert f"ontocraft_check-{__version__}-py3-none-any.whl" in demo


def test_rule_explanations_updated():
    assert "--registry-match" in rule_info("REG01")["meaning"]
    assert "--ignore-names" in rule_info("P22")["meaning"]
    assert "--cq-profile ontoflow" in rule_info("CQ01")["meaning"]
