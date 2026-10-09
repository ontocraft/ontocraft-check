"""논리 검사입니다.

기본 경로는 owlrl로 OWL 2 RL 규칙 폐포를 만든 뒤 모순을 찾습니다. OWL 2 RL 규칙 수준의
일관성만 보며, OWL 2 DL의 만족불가 클래스 판정은 HermiT 같은 DL 추론기가 필요합니다.
--reasoner hermit를 주면 Java와 owlready2가 있을 때만 HermiT로 만족불가 클래스를 찾습니다.
"""

from __future__ import annotations

import itertools
import shutil
import subprocess
import tempfile
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ..graph import find_individuals, rdf_list
from ..model import Finding, Report

CAT = "logic"
ERRNS = "http://www.daml.org/2002/03/agents/agent-ont#"

LIMIT_NOTE = (
    "OWL 2 RL 규칙 수준의 일관성만 봅니다. OWL 2 DL의 만족불가 클래스 판정은 HermiT 같은 DL 추론기가 필요합니다."
)

# 아래 세 종류는 이 모듈이 직접 찾으므로 owlrl 오류 메시지에서는 뺍니다.
_OWN_PATTERNS = ("'sameAs' and 'differentFrom'", "'sameAs' and 'AllDifferent'", "Disjoint classes", "of type 'Nothing'")


def closure(tbox: Graph, data: Graph | None) -> tuple[Graph, list[str]]:
    import owlrl

    g = Graph()
    for t in tbox:
        g.add(t)
    if data is not None:
        for t in data:
            g.add(t)
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False, datatype_axioms=False).expand(g)
    errors = []
    for node in list(g.subjects(RDF.type, URIRef(ERRNS + "ErrorMessage"))):
        for msg in g.objects(node, URIRef(ERRNS + "error")):
            errors.append(str(msg))
    return g, sorted(set(errors))


def disjoint_pairs(g: Graph) -> set:
    pairs = set()
    for a, b in g.subject_objects(OWL.disjointWith):
        pairs.add(frozenset((a, b)))
    for node in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members = rdf_list(g, g.value(node, OWL.members))
        pairs.update(frozenset(p) for p in itertools.combinations(members, 2))
    for _, head in g.subject_objects(OWL.disjointUnionOf):
        members = rdf_list(g, head)
        pairs.update(frozenset(p) for p in itertools.combinations(members, 2))
    return {p for p in pairs if len(p) == 2}


def different_pairs(g: Graph) -> set:
    pairs = {frozenset((a, b)) for a, b in g.subject_objects(OWL.differentFrom) if a != b}
    for node in g.subjects(RDF.type, OWL.AllDifferent):
        head = g.value(node, OWL.members) or g.value(node, OWL.distinctMembers)
        members = rdf_list(g, head)
        pairs.update(frozenset(p) for p in itertools.combinations(members, 2) if p[0] != p[1])
    return pairs


def check(tbox: Graph, data: Graph | None, report: Report, reasoner: str = "rl") -> None:
    try:
        g, errors = closure(tbox, data)
    except Exception as exc:  # owlrl 내부 오류는 검사 실패로 알립니다
        report.skip(CAT, "OWL 2 RL 폐포(owlrl)", f"owlrl 실행 중 오류가 났습니다: {type(exc).__name__}: {exc}")
        _hermit(tbox, data, report, reasoner)
        return

    individuals = find_individuals(g, set())
    nothing = set(g.subjects(RDF.type, OWL.Nothing))
    for x in sorted(nothing, key=str):
        report.add(Finding(
            CAT, "LOGIC01", "critical", str(x),
            "OWL 2 RL 추론 결과 이 개체가 owl:Nothing(어떤 개체도 속할 수 없는 클래스)에 속합니다. 온톨로지와 데이터가 모순입니다.",
            "이 개체의 타입과 이 개체가 속하게 된 클래스의 공리(owl:equivalentClass, 제약)를 거슬러 올라가 모순된 쪽을 고칩니다.",
        ))

    pairs = disjoint_pairs(g)
    seen = set()
    for pair in sorted(pairs, key=lambda p: sorted(map(str, p))):
        a, b = sorted(pair, key=str)
        # owl:Nothing의 개체는 모든 클래스에 속하므로 LOGIC01 로만 알립니다.
        both = (set(g.subjects(RDF.type, a)) & set(g.subjects(RDF.type, b))) - nothing
        for x in sorted(both, key=str):
            key = (x, a, b)
            if key in seen:
                continue
            seen.add(key)
            report.add(Finding(
                CAT, "LOGIC02", "critical", str(x),
                f"개체가 서로소로 선언된 두 클래스 {a}와 {b}에 동시에 속합니다(OWL 2 RL 추론 포함).",
                "개체의 타입 선언이나 이 타입을 끌어낸 도메인·레인지 공리를 고칩니다. 두 클래스가 실제로 겹칠 수 있다면 서로소 공리를 지웁니다.",
                {"classes": [str(a), str(b)]},
            ))

    for pair in sorted(different_pairs(g), key=lambda p: sorted(map(str, p))):
        a, b = sorted(pair, key=str)
        if (a, OWL.sameAs, b) in g or (b, OWL.sameAs, a) in g:
            report.add(Finding(
                CAT, "LOGIC03", "critical", f"{a}, {b}",
                "두 개체가 owl:differentFrom(또는 owl:AllDifferent)으로 다르다고 선언됐는데, 추론 결과 owl:sameAs로 같습니다.",
                "owl:sameAs를 만든 원인(함수 속성, 역함수 속성, 최대 카디널리티 1 등)을 찾아 둘 가운데 틀린 쪽을 고칩니다.",
                {"members": [str(a), str(b)]},
            ))

    for msg in errors:
        if any(p in msg for p in _OWN_PATTERNS):
            continue
        report.add(Finding(
            CAT, "LOGIC04", "critical", "owlrl",
            f"OWL 2 RL 규칙이 모순을 보고했습니다(owlrl 원문): {msg}",
            "원문에 나온 속성·개체의 공리와 값을 확인합니다.",
        ))

    report.stats["logic_individuals"] = len(individuals)
    report.stats["logic_closure_triples"] = len(g)
    report.ran.append("logic")
    _hermit(tbox, data, report, reasoner)


def java_available() -> bool:
    """java 실행 파일이 있고 실제로 실행되는지 봅니다. macOS의 /usr/bin/java는 JDK가 없으면 실패하는 껍데기입니다."""
    path = shutil.which("java")
    if not path:
        return False
    try:
        r = subprocess.run([path, "-version"], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _hermit(tbox: Graph, data: Graph | None, report: Report, reasoner: str) -> None:
    if reasoner != "hermit":
        return
    name = "만족불가 클래스(HermiT)"
    if not java_available():
        report.skip(CAT, name, "실행 가능한 Java가 없어 HermiT를 돌리지 않았습니다.")
        return
    try:
        import owlready2  # noqa: F401
    except ImportError:
        report.skip(CAT, name, "owlready2가 설치되지 않았습니다. `uv sync --extra hermit`로 설치합니다.")
        return
    try:
        unsat = run_hermit(tbox, data)
    except Exception as exc:
        if type(exc).__name__ == "OwlReadyInconsistentOntologyError":
            report.add(Finding(
                CAT, "LOGIC05", "critical", report.source,
                "HermiT(OWL 2 DL 추론기)가 온톨로지와 데이터 전체를 비일관으로 판정했습니다.",
                "위의 OWL 2 RL 결과에서 모순을 먼저 고치고, 남으면 서로소·카디널리티 공리를 하나씩 빼 보며 원인을 좁힙니다.",
            ))
            report.ran.append("logic-hermit")
            return
        report.skip(CAT, name, f"HermiT 실행 중 오류가 났습니다: {type(exc).__name__}: {str(exc)[:300]}")
        return
    for c in unsat:
        report.add(Finding(
            CAT, "LOGIC05", "critical", c,
            "HermiT(OWL 2 DL 추론기)가 이 클래스를 만족불가로 판정했습니다. 어떤 개체도 이 클래스에 속할 수 없습니다.",
            "이 클래스의 상위 클래스·제약·서로소 공리 가운데 서로 부딪히는 것을 찾아 고칩니다.",
        ))
    report.ran.append("logic-hermit")


def run_hermit(tbox: Graph, data: Graph | None) -> list[str]:  # pragma: no cover - Java가 있는 환경에서만 실행
    import owlready2

    g = Graph()
    for t in tbox:
        g.add(t)
    if data is not None:
        for t in data:
            g.add(t)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.owl"
        g.serialize(destination=str(path), format="xml")
        world = owlready2.World()
        onto = world.get_ontology(path.as_uri()).load()
        with onto:
            owlready2.sync_reasoner_hermit(world, infer_property_values=False, debug=0)
        return sorted(c.iri for c in world.inconsistent_classes() if c is not owlready2.Nothing)
