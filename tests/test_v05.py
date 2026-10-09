"""0.5.0에서 더한 규칙: 선언되지 않은 데이터 타입(DT01), 종류가 다른 요소의 같은 레이블(LBL01), 객체 속성끼리의 같은 레이블(LBL02)."""

import json

import pytest

from helpers import run
from ontocraft_check import __version__
from ontocraft_check.checks.pitfalls import is_builtin_datatype, norm_label
from ontocraft_check.render import RULE_TITLES, render
from ontocraft_check.rules import all_rules, rule_info
from rdflib import URIRef

HEAD = """@prefix ex:   <https://example.org/v5#> .
@prefix geo:  <http://www.opengis.net/ont/geosparql#> .
@prefix owl:  <http://www.w3.org/2002/07/owl#> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
<https://example.org/v5> a owl:Ontology .
ex:Vessel a owl:Class ; rdfs:label "선박"@ko .
ex:Port a owl:Class ; rdfs:label "항구"@ko .
"""


@pytest.fixture
def check(tmp_path):
    def _run(body: str):
        p = tmp_path / "o.ttl"
        p.write_text(HEAD + body, encoding="utf-8")
        return run(str(p))
    return _run


def hits(report, rule):
    return [x for x in report.findings if x.rule == rule]


def test_version():
    assert __version__ == "0.5.0"


def test_new_rules_listed_and_explained():
    for rid, sev in (("DT01", "important"), ("LBL01", "minor"), ("LBL02", "minor")):
        assert rid in RULE_TITLES
        info = rule_info(rid.lower())
        assert info["severity"] == sev and info["category"] == "pitfall"
        assert "note" not in info  # OOPS! 번호가 아닌 이 도구의 규칙입니다
    assert "rdfs:Datatype" in rule_info("DT01")["fix"]
    assert "동사구" in rule_info("LBL01")["fix"]
    assert {r["rule"] for r in all_rules()} >= {"DT01", "LBL01", "LBL02"}


# DT01

def test_dt01_catches_undeclared_datatype_and_counts_uses(check):
    r = check("""
ex:geom a owl:DatatypeProperty ; rdfs:domain ex:Vessel ; rdfs:range geo:wktLiteral .
ex:area a owl:DatatypeProperty ; rdfs:domain ex:Port ; rdfs:range geo:wktLiteral .
ex:Port rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:area ; owl:allValuesFrom geo:wktLiteral ] .
""")
    (h,) = hits(r, "DT01")
    assert h.target == "http://www.opengis.net/ont/geosparql#wktLiteral"
    assert h.severity == "important"
    assert h.detail["count"] == 3
    assert h.detail["properties"] == ["https://example.org/v5#area", "https://example.org/v5#geom"]
    assert "geo:wktLiteral a rdfs:Datatype ." in h.fix
    assert not [x for x in r.findings if x.rule == "P34-EXT" and "wktLiteral" in x.target]


def test_dt01_catches_own_namespace_datatype(check):
    r = check("ex:code a owl:DatatypeProperty ; rdfs:domain ex:Vessel ; rdfs:range ex:ImoNumber .\n")
    assert [x.target for x in hits(r, "DT01")] == ["https://example.org/v5#ImoNumber"]


def test_dt01_releases_declared_and_builtin_datatypes(check):
    r = check("""
geo:wktLiteral a rdfs:Datatype .
ex:geom a owl:DatatypeProperty ; rdfs:range geo:wktLiteral .
ex:name a owl:DatatypeProperty ; rdfs:range rdf:langString .
ex:n1 a owl:DatatypeProperty ; rdfs:range xsd:string .
ex:n2 a owl:DatatypeProperty ; rdfs:range xsd:dateTimeStamp .
ex:n3 a owl:DatatypeProperty ; rdfs:range rdfs:Literal .
ex:n4 a owl:DatatypeProperty ; rdfs:range owl:real .
ex:n5 a owl:DatatypeProperty ; rdfs:range rdf:PlainLiteral .
ex:n6 a owl:DatatypeProperty ; rdfs:range rdf:XMLLiteral .
ex:n7 a owl:DatatypeProperty ; rdfs:range rdf:HTML .
ex:n8 a owl:DatatypeProperty ; rdfs:range rdf:JSON .
ex:n9 a owl:DatatypeProperty ; rdfs:range owl:rational .
ex:n10 a owl:DatatypeProperty ; rdfs:range [ a rdfs:Datatype ; owl:onDatatype xsd:integer ;
    owl:withRestrictions ( [ xsd:minInclusive 0 ] ) ] .
""")
    assert hits(r, "DT01") == []


def test_dt01_leaves_non_data_property_ranges_to_p34(check):
    r = check("""
ex:at a owl:ObjectProperty ; rdfs:domain ex:Vessel ; rdfs:range geo:Feature .
ex:loose a rdf:Property ; rdfs:range geo:wktLiteral .
""")
    assert hits(r, "DT01") == []
    ext = {x.target for x in hits(r, "P34-EXT")}
    assert "http://www.opengis.net/ont/geosparql#Feature" in ext


def test_dt01_skips_name_declared_as_class(check):
    r = check("ex:size a owl:DatatypeProperty ; rdfs:range ex:Port .\n")
    assert hits(r, "DT01") == []


def test_builtin_datatype_helper():
    assert is_builtin_datatype(URIRef("http://www.w3.org/2001/XMLSchema#gYear"))
    assert is_builtin_datatype(URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON"))
    assert not is_builtin_datatype(URIRef("http://www.opengis.net/ont/geosparql#wktLiteral"))


# LBL01

def test_lbl01_catches_class_and_property_with_same_label(check):
    r = check("""
ex:PortCall a owl:Class ; rdfs:label "입항"@ko .
ex:arrivedAt a owl:ObjectProperty ; rdfs:label " 입항 "@ko ; rdfs:domain ex:Vessel ; rdfs:range ex:Port .
ex:Anchoring a owl:Class ; rdfs:label "정박"@ko .
ex:anchoredAt a owl:ObjectProperty ; rdfs:label "정박"@ko ; rdfs:domain ex:Vessel ; rdfs:range ex:Port .
""")
    got = {tuple(x.detail["members"]) for x in hits(r, "LBL01")}
    assert got == {
        ("https://example.org/v5#PortCall", "https://example.org/v5#arrivedAt"),
        ("https://example.org/v5#Anchoring", "https://example.org/v5#anchoredAt"),
    }
    h = hits(r, "LBL01")[0]
    assert h.severity == "minor" and "동사구" in h.fix
    assert h.detail["kinds"]["https://example.org/v5#arrivedAt"] == "object"


def test_lbl01_catches_data_and_annotation_kinds(check):
    r = check("""
ex:Draft a owl:Class ; rdfs:label "흘수"@ko .
ex:draft a owl:DatatypeProperty ; rdfs:label "흘수"@ko ; rdfs:range xsd:decimal .
ex:note a owl:AnnotationProperty ; rdfs:label "비고"@ko .
ex:remark a owl:DatatypeProperty ; rdfs:label "비고"@ko ; rdfs:range xsd:string .
""")
    assert {x.detail["label"] for x in hits(r, "LBL01")} == {"흘수", "비고"}


def test_lbl01_releases_same_kind_different_language_and_range_named(check):
    r = check("""
ex:Vessel_draft a owl:DatatypeProperty ; rdfs:label "흘수"@ko ; rdfs:range xsd:decimal .
ex:ModelShip_draft a owl:DatatypeProperty ; rdfs:label "흘수"@ko ; rdfs:range xsd:decimal .
ex:Call a owl:Class ; rdfs:label "call"@en .
ex:call a owl:ObjectProperty ; rdfs:label "call"@de ; rdfs:range ex:Port .
ex:Genre a owl:Class ; rdfs:label "장르"@ko .
ex:genre a owl:ObjectProperty ; rdfs:label "장르"@ko ; rdfs:range ex:Genre .
""")
    assert hits(r, "LBL01") == []
    assert hits(r, "LBL02") == []


def test_lbl01_does_not_repeat_p32(check):
    r = check("""
ex:Harbor a owl:Class ; rdfs:label "항구"@ko .
""")
    assert hits(r, "LBL01") == [] and len(hits(r, "P32")) == 1


# LBL02

def test_lbl02_catches_object_properties_with_same_label(check):
    r = check("""
ex:memberOf a owl:ObjectProperty ; rdfs:label "소속"@ko ; rdfs:range ex:Port .
ex:belongsTo a owl:ObjectProperty ; rdfs:label "소속"@ko ; rdfs:range ex:Vessel .
""")
    (h,) = hits(r, "LBL02")
    assert h.severity == "minor"
    assert h.detail["members"] == ["https://example.org/v5#belongsTo", "https://example.org/v5#memberOf"]
    assert "구분이 어렵습니다" in h.message
    assert hits(r, "LBL01") == []


def test_lbl02_releases_equivalent_properties(check):
    r = check("""
ex:memberOf a owl:ObjectProperty ; rdfs:label "소속"@ko ; owl:equivalentProperty ex:belongsTo .
ex:belongsTo a owl:ObjectProperty ; rdfs:label "소속"@ko .
""")
    assert hits(r, "LBL02") == []


def test_norm_label():
    assert norm_label("  입항\t 시각 ") == "입항 시각"


def test_new_rules_in_reports_and_disable(check):
    body = """
ex:geom a owl:DatatypeProperty ; rdfs:range geo:wktLiteral .
ex:PortCall a owl:Class ; rdfs:label "입항"@ko .
ex:arrivedAt a owl:ObjectProperty ; rdfs:label "입항"@ko ; rdfs:range ex:Port .
"""
    r = check(body)
    md = render(r, "md")
    assert "선언되지 않은 데이터 타입" in md and "종류가 다른 요소의 같은 레이블" in md
    assert "DT01, LBL01, LBL02는 OOPS! 번호가 아닌" in md
    d = json.loads(render(r, "json"))
    assert {"DT01", "LBL01"} <= {x["rule"] for x in d["findings"]}
    assert r.worst_at_least("important")
