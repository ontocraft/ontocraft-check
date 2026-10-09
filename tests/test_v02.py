"""0.2.0에서 더한 기능: 등록부 분야 구분, 일치 신뢰도, 항목 묶기, 규칙 끄기."""

import json
import os
import re
from pathlib import Path

import pytest

from helpers import f, local, run
from ontocraft_check import __version__
from ontocraft_check.checks.registry import list_domains
from ontocraft_check.cli import main
from ontocraft_check.render import render

REG = f("registry-multi")
WRONG_DOMAIN = {
    ("Measurement", "semiconductor", "fab-metrology"),
    ("Service", "physical-ai", "ros-service"),
    ("Sensor", "smartcity", "city-iot-sensor"),
    ("Observation", "smartcity", "sensor-observation"),
    ("ContainerCargo", "port", "shipping-container"),
}
# 정본 등록부 폴더(aki-space 의 data/registry)가 있으면 환경 변수로 줍니다. 없으면 이 시험은 건너뜁니다.
REAL_REGISTRY = Path(os.environ.get("ONTOCRAFT_REGISTRY_DIR") or "/nonexistent")
WEB = Path(__file__).resolve().parents[1] / "web"


def triples(report, rule):
    return {(local(x.target), x.detail["domain"], x.detail["term_id"]) for x in report.findings if x.rule == rule}


def test_version():
    assert __version__ == "0.7.2"
    assert "ontocraft-check 0.7.2으로 만들었습니다" in render(run(f("clean.ttl")), "md")


def test_all_domains_shows_domain_on_each_candidate():
    r = run(f("maritime-like.ttl"), registry_dir=REG)
    reg = r.by_category("registry")
    assert {x.rule for x in reg} == {"REG01"}
    assert WRONG_DOMAIN <= triples(r, "REG01")
    # 선박은 maritime 과 port 두 분야에 있어 후보가 둘입니다.
    assert {("Vessel", "maritime", "ship"), ("Vessel", "port", "vessel-call")} <= triples(r, "REG01")
    for x in reg:
        assert x.detail["domain_name"]
        assert f"{x.detail['domain']}({x.detail['domain_name']}) 분야" in x.message


def test_domains_moves_other_domain_matches_to_reg02():
    # 0.4 부터 관련 분야(port)를 함께 보므로, 0.2 의 분야 나누기는 strict 로 시험합니다.
    r = run(f("maritime-like.ttl"), registry_dir=REG, domains=["maritime"], strict_domains=True)
    assert triples(r, "REG01") == {("Vessel", "maritime", "ship"), ("Tanker", "maritime", "oil-tanker")}
    assert triples(r, "REG02") == WRONG_DOMAIN
    assert all(x.severity == "info" for x in r.by_category("registry"))
    assert all("다른 분야에서 같은 이름이 있습니다(뜻이 다를 수 있음)" in x.message for x in r.findings if x.rule == "REG02")
    md = render(r, "md")
    assert "### REG02 다른 분야에서 같은 이름이 있음(뜻이 다를 수 있음) (정보, 5건)" in md
    assert "| 고른 분야 | maritime |" in md
    assert r.stats["registry_selected_domains"] == ["maritime"]


def test_domains_string_and_unknown_domain():
    r = run(f("maritime-like.ttl"), registry_dir=REG, domains="maritime, nope")
    assert r.options["domains"] == ["maritime", "nope"]
    assert r.stats["registry_unknown_domains"] == ["nope"]
    assert "등록부에 없는 분야 id입니다: nope." in render(r, "md")


def test_confidence_high_for_ko_low_for_alt():
    r = run(f("maritime-like.ttl"), registry_dir=REG, domains=["maritime"])
    by = {local(x.target): x for x in r.findings if x.rule == "REG01"}
    assert by["Vessel"].detail["confidence"] == "높음"
    assert by["Vessel"].detail["matched_field"] == "ko"
    assert by["Tanker"].detail["confidence"] == "낮음"
    assert "동의어로 맞은 것이라 상위·하위 개념일 수 있습니다(예: Tanker와 유조선)" in by["Tanker"].message
    assert "일치 신뢰도는 높음입니다." in by["Vessel"].message
    assert "상위·하위" not in by["Vessel"].message
    assert "「선박」이 등록부" in by["Vessel"].message and "「탱커」가 등록부" in by["Tanker"].message
    d = json.loads(render(r, "json"))
    assert {x["detail"]["confidence"] for x in d["findings"] if x["rule"] == "REG01"} == {"높음", "낮음"}


def test_list_domains():
    ids = {d["id"]: d["name"] for d in list_domains(REG)}
    assert ids == {"maritime": "해양·조선", "semiconductor": "반도체", "physical-ai": "Physical AI",
                   "smartcity": "스마트시티", "port": "항만·물류"}
    # 0.1 시험용 등록부: domains.json, candidates.json 은 분야 목록에 넣지 않습니다.
    assert [d["id"] for d in list_domains(f("registry"))] == ["sample"]


@pytest.mark.skipif(not REAL_REGISTRY.is_dir(), reason="ONTOCRAFT_REGISTRY_DIR 가 없습니다")
def test_real_registry_wrong_domain_examples():
    r = run(f("maritime-like.ttl"), registry_dir=str(REAL_REGISTRY), domains=["maritime"], strict_domains=True)
    assert WRONG_DOMAIN <= triples(r, "REG02")
    assert not {t for t in triples(r, "REG01") if t[1] != "maritime"}


def test_cli_domains(tmp_path):
    out = tmp_path / "r.json"
    main([f("maritime-like.ttl"), "--registry", REG, "--domains", "maritime", "--strict-domains",
          "--format", "json", "--out", str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["options"]["domains"] == ["maritime"]
    assert sum(1 for x in d["findings"] if x["rule"] == "REG02") == 5


def test_disable_rules_and_header():
    base = run(f("pitfalls.ttl"))
    n13 = sum(1 for x in base.findings if x.rule == "P13")
    assert n13 > 0
    r = run(f("pitfalls.ttl"), disable="p13,P22,NOPE")
    assert not [x for x in r.findings if x.rule in ("P13", "P22")]
    assert r.options["disabled"] == ["P13", "P22", "NOPE"]
    assert r.options["disabled_counts"]["P13"] == n13
    assert len(r.findings) == len(base.findings) - n13 - r.options["disabled_counts"]["P22"]
    for fmt in ("md", "html"):
        text = render(r, fmt)
        assert f"사용자가 끈 규칙: P13 역관계(owl:inverseOf) 없음(뺀 항목 {n13}건)" in text
        assert "이 도구에 없는 규칙 id입니다: NOPE." in text
    assert json.loads(render(r, "json"))["options"]["disabled"] == ["P13", "P22", "NOPE"]


def test_disable_changes_exit_code(capsys):
    assert main([f("pitfalls.ttl")]) == 1  # P06·P19가 치명입니다
    assert main([f("pitfalls.ttl"), "--disable", "P06,P19"]) == 0
    capsys.readouterr()


def test_p13_mentions_lpg():
    r = run(f("pitfalls.ttl"))
    p13 = [x for x in r.findings if x.rule == "P13"]
    assert p13 and all("속성 그래프(LPG) 기반 설계에서는 역관계를 일부러 두지 않는 경우가 흔합니다" in x.message for x in p13)


@pytest.fixture
def many_props(tmp_path):
    lines = ["@prefix ex: <https://example.org/m#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .",
             "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
             "<https://example.org/m> a owl:Ontology .", "ex:A a owl:Class ."]
    for i in range(12):
        lines.append(f"ex:p{i} a owl:ObjectProperty ; rdfs:domain ex:A ; rdfs:range ex:A .")
    p = tmp_path / "many.ttl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def test_grouping_default(many_props):
    r = run(many_props)
    assert sum(1 for x in r.findings if x.rule == "P13") == 12
    md = render(r, "md")
    assert "| 경미 | P13 | 12개 요소 |" in md
    assert "<details><summary>대상 12개 보기</summary>" in md
    assert md.count("| 경미 | P13 |") == 1
    html = render(r, "html")
    assert "<details><summary>대상 12개 보기</summary><ul>" in html
    assert "<td>12개 요소</td>" in html
    d = json.loads(render(r, "json"))
    assert sum(1 for x in d["findings"] if x["rule"] == "P13") == 12  # findings 는 그대로입니다
    g = [x for x in d["grouped"] if x["rule"] == "P13"]
    assert g and g[0]["count"] == 12 and len(g[0]["targets"]) == 12 and g[0]["severity"] == "minor"


def test_grouping_limits(many_props):
    md = render(run(many_props, group_over=0), "md")
    assert "개 요소" not in md and "<details>" not in md
    assert md.count("| 경미 | P13 |") == 12
    assert "묶지 않습니다" in md
    assert json.loads(render(run(many_props, group_over=0), "json"))["grouped"] == []
    assert "12개 요소" in render(run(many_props, group_over=11), "md")
    assert "12개 요소" not in render(run(many_props, group_over=12), "md")


def test_grouping_does_not_change_counts(many_props):
    a, b = run(many_props, group_over=0), run(many_props, group_over=3)
    assert a.summary() == b.summary()


def test_grouped_targets_keep_differing_messages():
    r = run(f("maritime-like.ttl"), registry_dir=REG, domains=["maritime"], group_over=2, strict_domains=True)
    md = render(r, "md")
    assert "| 정보 | REG02 | 5개 요소 | REG02 항목이 5개입니다." in md
    # 설명이 대상마다 다르므로 목록에 대상과 설명을 함께 적습니다.
    assert re.search(r"- https://example.org/flux#Sensor: 다른 분야에서 같은 이름이 있습니다", md)


def test_cli_group_over_and_bad_value(many_props, capsys):
    assert main([many_props, "--group-over", "0", "--fail-on", "none"]) == 0
    assert "개 요소" not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main([many_props, "--group-over", "-1"])
    capsys.readouterr()


def test_web_files_follow_new_version():
    worker = (WEB / "ontocraft-check-worker.js").read_text(encoding="utf-8")
    demo = (WEB / "demo.html").read_text(encoding="utf-8")
    for key in ("domains", "disable", "group_over"):
        assert key in worker
    assert f"ontocraft_check-{__version__}-py3-none-any.whl" in demo
    assert "P13" in demo
