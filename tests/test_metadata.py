from helpers import f, rules_and_targets, run


def test_label_languages():
    r = run(f("metadata.ttl"))
    meta = {x.rule: x for x in r.findings if x.category == "metadata"}
    assert set(meta) == {"META02", "META03"}
    assert meta["META02"].detail["targets"] == ["https://example.org/meta#EnglishOnly"]
    assert meta["META03"].detail["targets"] == ["https://example.org/meta#KoreanOnly"]
    assert meta["META02"].severity == "minor"


def test_missing_label_and_version():
    r = run(f("pitfalls.ttl"))
    got = rules_and_targets(r, "metadata")
    assert ("META04", "Truck") in got
    assert ("META01", "https://example.org/bad") in got
    sev = {x.rule: x.severity for x in r.findings if x.category == "metadata"}
    assert sev["META04"] == "important" and sev["META01"] == "minor"
    # 레이블이 없는 요소는 @ko·@en 수에 다시 넣지 않습니다
    assert not any(x.rule in ("META02", "META03") and "Truck" in str(x.detail) for x in r.findings)


def test_clean_metadata():
    r = run(f("clean.ttl"))
    assert not r.by_category("metadata")
