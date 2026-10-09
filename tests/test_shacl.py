from helpers import f, local, run


def test_violations_with_focus_and_path():
    r = run(f("clean.ttl"), data=f("bad-data.ttl"), shapes=f("clean-shapes.ttl"))
    items = r.by_category("shacl")
    focus = {local(x.target) for x in items}
    assert focus == {"park", "beta"}
    assert all(x.severity == "critical" for x in items)
    assert all(x.detail["path"] == "ex:name" for x in items)
    assert any("이름이 있어야" in x.message for x in items)
    assert r.stats["shacl_conforms"] is False


def test_conforming_data():
    r = run(f("clean.ttl"), data=f("clean-data.ttl"), shapes=f("clean-shapes.ttl"))
    assert "shacl" in r.ran and not r.by_category("shacl")


def test_tbox_subclass_is_used_for_targets():
    # 형상은 ex:Agent를 겨누고 데이터는 ex:Person입니다. TBox를 합쳐야 잡힙니다.
    r = run(f("clean.ttl"), data=f("bad-data.ttl"), shapes=f("clean-shapes.ttl"))
    assert "park" in {local(x.target) for x in r.by_category("shacl")}


def test_skipped_without_shapes_or_data():
    for kw in ({}, {"data": f("clean-data.ttl")}, {"shapes": f("clean-shapes.ttl")}):
        r = run(f("clean.ttl"), **kw)
        assert "shacl" not in r.ran
        assert [k for k in r.skipped if k.category == "shacl"]
