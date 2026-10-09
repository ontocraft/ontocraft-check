from helpers import f, local, run
from ontocraft_check.checks import logic


def test_rl_contradictions():
    r = run(f("logic.ttl"), data=f("logic-data.ttl"))
    got = {(x.rule, local(x.target)) for x in r.by_category("logic")}
    assert ("LOGIC01", "ghost") in got
    assert ("LOGIC02", "tom") in got
    l3 = [x for x in r.by_category("logic") if x.rule == "LOGIC03"]
    assert [x.detail["members"] for x in l3] == [["https://example.org/logic#m1", "https://example.org/logic#m2"]]
    assert any(rule == "LOGIC04" for rule, _ in got)
    # owl:Nothing의 개체는 서로소 위반으로 겹쳐 알리지 않습니다
    assert ("LOGIC02", "ghost") not in got
    assert all(x.severity == "critical" for x in r.by_category("logic"))


def test_clean_is_consistent():
    r = run(f("clean.ttl"), data=f("clean-data.ttl"))
    assert "logic" in r.ran
    assert not r.by_category("logic")


def test_hermit_skipped_without_java(monkeypatch):
    monkeypatch.setattr(logic.shutil, "which", lambda name: None)
    r = run(f("clean.ttl"), reasoner="hermit")
    skips = [k for k in r.skipped if k.category == "logic"]
    assert len(skips) == 1 and "Java" in skips[0].reason
    assert "logic" in r.ran and "logic-hermit" not in r.ran


def test_hermit_in_this_environment():
    r = run(f("clean.ttl"), reasoner="hermit")
    if not logic.java_available():
        assert any("Java" in k.reason for k in r.skipped)


def test_rl_default_does_not_mention_hermit():
    r = run(f("clean.ttl"))
    assert not [k for k in r.skipped if k.category == "logic"]
