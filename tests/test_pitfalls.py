import pytest

from helpers import f, rules_and_targets, run
from ontocraft_check.checks.pitfalls import name_style, strongly_connected

BAD = run(f("pitfalls.ttl"))
CLEAN = run(f("clean.ttl"))

EXPECTED = [
    ("P04", "Orphan"),
    ("P04", "loose"),
    ("P06", "Motor"),
    ("P08", "Orphan"),
    ("P10", "https://example.org/bad"),
    ("P11", "hasEngine"),
    ("P11", "loose"),
    ("P13", "hasEngine"),
    ("P19", "maker"),
    ("P22", "sports_car"),
    ("P32", "sports_car"),
    ("P34", "Boat"),
    ("P34-EXT", "Concept"),
    ("P35", "weight"),
    ("P35-EXT", "note"),
    ("P41", "https://example.org/bad"),
    ("LBL01", "hasEngine"),  # 0.5.0: 클래스 Engine 과 range 없는 객체 속성 hasEngine 이 둘 다 「엔진」
]


@pytest.mark.parametrize("rule,target", EXPECTED)
def test_bad_example_is_caught(rule, target):
    assert (rule, target) in rules_and_targets(BAD, "pitfall")


def test_bad_example_has_nothing_unexpected():
    assert rules_and_targets(BAD, "pitfall") == set(EXPECTED)


@pytest.mark.parametrize("rule", sorted({r for r, _ in EXPECTED} | {"P38"}))
def test_clean_example_is_released(rule):
    assert not [x for x in CLEAN.findings if x.rule == rule]


def test_group_members():
    p06 = next(x for x in BAD.findings if x.rule == "P06")
    assert p06.detail["members"] == ["https://example.org/bad#Engine", "https://example.org/bad#Motor"]
    p32 = next(x for x in BAD.findings if x.rule == "P32")
    assert p32.detail["members"] == ["https://example.org/bad#Car", "https://example.org/bad#sports_car"]
    assert p32.detail["label"] == "자동차" and p32.detail["lang"] == "ko"


def test_severities():
    sev = {x.rule: x.severity for x in BAD.findings}
    assert sev["P06"] == "critical" and sev["P19"] == "critical"
    assert sev["P10"] == "important" and sev["P11"] == "important"
    assert sev["P34"] == "important" and sev["P35"] == "important" and sev["P41"] == "important"
    assert sev["P34-EXT"] == "minor" and sev["P35-EXT"] == "minor"
    for r in ("P04", "P08", "P13", "P22", "P32"):
        assert sev[r] == "minor"


def test_p13_message_says_not_always_right():
    msg = next(x.message for x in BAD.findings if x.rule == "P13")
    assert "늘 맞지는 않습니다" in msg


def test_p19_mentions_intersection():
    msg = next(x.message for x in BAD.findings if x.rule == "P19")
    assert "교집합" in msg


def test_p38_without_ontology_declaration():
    r = run(f("no-ontology.ttl"))
    rules = {x.rule for x in r.findings}
    assert "P38" in rules
    assert "P41" not in rules and "META01" not in rules
    assert "P10" not in rules  # owl:disjointWith가 있습니다


@pytest.mark.parametrize("name,style", [
    ("SportsCar", "UpperCamel"), ("Car", "UpperCamel"), ("CCTV", "UpperCamel"),
    ("sportsCar", "lowerCamel"), ("sports_car", "snake"), ("sports-car", "kebab"),
    ("car", "lower"), ("자동차", "other"), ("Sports_car-x", "other"),
])
def test_name_style(name, style):
    assert name_style(name) == style


def test_cycle_detection():
    comps = strongly_connected({"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}})
    assert {"a", "b", "c"} in comps
    assert all(len(c) == 1 for c in comps if "d" in c)
