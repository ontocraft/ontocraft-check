import json
import re

import pytest
from rdflib import Graph

from helpers import f, run
from ontocraft_check.cli import main
from ontocraft_check.render import render

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿✅❌⚠]")


def test_clean_report_has_no_findings():
    r = run(f("clean.ttl"), data=f("clean-data.ttl"), shapes=f("clean-shapes.ttl"))
    assert r.findings == []
    assert set(r.ran) >= {"pitfall", "metadata", "logic", "shacl"}


@pytest.mark.parametrize("fmt,suffix", [("xml", ".owl"), ("xml", ".rdf"), ("json-ld", ".jsonld"), ("nt", ".nt")])
def test_input_formats(tmp_path, fmt, suffix):
    g = Graph().parse(f("clean.ttl"))
    p = tmp_path / ("clean" + suffix)
    g.serialize(destination=str(p), format=fmt)
    r = run(str(p))
    base = run(f("clean.ttl"))
    assert r.triples == base.triples
    assert r.stats["classes"] == base.stats["classes"] == 3
    assert r.stats["object_properties"] == 3 and r.stats["data_properties"] == 1
    assert [x for x in r.findings if x.severity != "info"] == []


def test_wrong_extension_falls_back(tmp_path):
    p = tmp_path / "clean.owl"  # 확장자는 RDF/XML 이지만 내용은 Turtle입니다
    p.write_text(open(f("clean.ttl"), encoding="utf-8").read(), encoding="utf-8")
    assert run(str(p)).source_format == "turtle"


def test_exit_codes(capsys):
    assert main([f("clean.ttl"), "--fail-on", "minor"]) == 0
    assert main([f("pitfalls.ttl")]) == 1  # 기본 critical, P06·P19가 있습니다
    assert main([f("metadata.ttl"), "--fail-on", "critical"]) == 0
    assert main([f("metadata.ttl"), "--fail-on", "minor"]) == 1
    assert main([f("pitfalls.ttl"), "--fail-on", "none"]) == 0
    assert main([f("no-ontology.ttl"), "--fail-on", "important"]) == 1
    capsys.readouterr()


def test_unreadable_input_exit_2(tmp_path, capsys):
    p = tmp_path / "broken.ttl"
    p.write_text("this is not rdf <<<", encoding="utf-8")
    assert main([str(p)]) == 2
    assert main([str(tmp_path / "missing.ttl")]) == 2
    capsys.readouterr()


def test_out_and_json(tmp_path):
    out = tmp_path / "r.json"
    main([f("pitfalls.ttl"), "--format", "json", "--out", str(out), "--fail-on", "none"])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["summary"]["pitfall"]["critical"] == 2
    assert {"category", "rule", "severity", "severity_ko", "target", "message", "fix"} <= set(d["findings"][0])
    assert d["stats"]["classes"] == 7
    assert "OOPS! 자체의 결과가 아닙니다" in d["notice"]
    assert d["cannot_say"]


@pytest.mark.parametrize("fmt", ["md", "html"])
def test_report_text(fmt):
    r = run(f("logic.ttl"), data=f("logic-data.ttl"))
    text = render(r, fmt)
    for must in ("OOPS! 자체의 결과가 아닙니다", "이 보고서로 말할 수 없는 것", "OWL 2 RL 규칙 수준의 일관성만 봅니다",
                 "HermiT", "P01", "P05", "P31", "건너뛴 검사", "트리플 수", "모델링 함정", "데이터 제약"):
        assert must in text, must
    assert "—" not in text
    assert not EMOJI.search(text)


def test_markdown_tables_by_category():
    text = render(run(f("pitfalls.ttl")), "md")
    assert "### P06 rdfs:subClassOf 순환 (치명, 1건)" in text
    assert "| 심각도 | 규칙 | 대상 | 설명 | 고치는 방법 |" in text
