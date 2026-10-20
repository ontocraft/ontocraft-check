"""0.7.5: OWL 2 RL 로 드러나는 만족불가 클래스(LOGIC06)와 논리 검사 범위 표시."""

from ontocraft_check.render import render
from ontocraft_check.runner import run

TTL = """
@prefix : <http://example.org/u#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://example.org/u> a owl:Ontology .
:Impossible a owl:Class ; owl:equivalentClass owl:Nothing .
:Child a owl:Class ; rdfs:subClassOf :Impossible .
:Fine a owl:Class .
"""


def _run(tmp_path):
    f = tmp_path / "u.ttl"
    f.write_text(TTL, encoding="utf-8")
    return run(str(f))


def test_logic06_finds_rl_unsatisfiable_classes(tmp_path):
    r = _run(tmp_path)
    got = {x.target.rsplit("#", 1)[-1] for x in r.by_category("logic") if x.rule == "LOGIC06"}
    assert got == {"Impossible", "Child"}


def test_logic_status_says_rl_only(tmp_path):
    r = _run(tmp_path)
    md = render(r, "md")
    assert "OWL 2 RL 범위만" in md
    import json
    j = json.loads(render(r, "json"))
    assert "OWL 2 RL 범위만" in j["summary"]["logic"]["note"]


def test_logic_status_web_drops_cli_hint(tmp_path, monkeypatch):
    import sys

    from ontocraft_check.render import logic_status

    r = _run(tmp_path)
    assert "--reasoner hermit" in logic_status(r)
    monkeypatch.setattr(sys, "platform", "emscripten")
    s = logic_status(r)
    assert "OWL 2 RL 범위만" in s and "--reasoner" not in s
