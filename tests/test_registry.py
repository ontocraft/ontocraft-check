from helpers import f, local, run


def test_exact_match_candidates():
    r = run(f("clean.ttl"), registry_dir=f("registry"))
    got = {(local(x.target), x.detail["term_iri"]) for x in r.by_category("registry")}
    # 사람 = ko, 단체 = alt. 행위자(domains.json), 소속(candidates.json), 이름(폐기)은 대조하지 않습니다.
    assert got == {
        ("Person", "https://w3id.org/ontocraft/terms/person"),
        ("Organization", "https://w3id.org/ontocraft/terms/org"),
    }
    assert all(x.severity == "info" for x in r.by_category("registry"))
    assert all("skos:exactMatch 후보: https://w3id.org/ontocraft/terms/" in x.message for x in r.by_category("registry"))
    assert r.stats["registry_files"] == ["sample.json"]


def test_info_does_not_fail():
    r = run(f("clean.ttl"), registry_dir=f("registry"))
    assert not r.worst_at_least("minor")


def test_skipped_without_registry():
    r = run(f("clean.ttl"))
    assert "registry" not in r.ran


def test_local_name_fallback(tmp_path):
    p = tmp_path / "x.ttl"
    p.write_text(
        "@prefix ex: <https://example.org/x#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "ex:사람 a owl:Class .\n", encoding="utf-8")
    r = run(str(p), registry_dir=f("registry"))
    assert [x.detail["matched_text"] for x in r.by_category("registry")] == ["사람"]
