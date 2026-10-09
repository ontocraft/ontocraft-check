"""메타데이터·명명 검사입니다. 검사 범위는 온톨로지 파일(TBox)입니다."""

from __future__ import annotations

from rdflib.namespace import OWL, RDFS

from ..graph import Inventory, has_lang, ontology_iri
from ..model import Finding, Report

CAT = "metadata"


def check(inv: Inventory, report: Report) -> None:
    g = inv.graph
    if inv.ontologies:
        has_version = any(
            (o, OWL.versionInfo, None) in g or (o, OWL.versionIRI, None) in g for o in inv.ontologies
        )
        if not has_version:
            report.add(Finding(
                CAT, "META01", "minor", ontology_iri(inv) or str(inv.ontologies[0]),
                "온톨로지 선언에 owl:versionInfo와 owl:versionIRI가 모두 없습니다. 어느 버전을 검사했는지 남지 않습니다.",
                "owl:versionInfo \"1.0\" 이나 owl:versionIRI <.../1.0>을 붙입니다.",
            ))

    no_label, no_ko, no_en = [], [], []
    entities = inv.entities - inv.ignored  # 0.7: --ignore-names 로 뺀 요소는 레이블 규칙에서도 뺍니다
    for e in sorted(entities, key=str):
        labels = list(g.objects(e, RDFS.label))
        if not labels:
            no_label.append(e)
            continue
        if not any(has_lang(l, "ko") for l in labels):
            no_ko.append(e)
        if not any(has_lang(l, "en") for l in labels):
            no_en.append(e)

    for e in no_label:
        kind = "클래스" if e in inv.classes else "속성"
        report.add(Finding(
            CAT, "META04", "important", str(e),
            f"{kind}에 rdfs:label이 하나도 없습니다. 화면과 보고서에 IRI가 그대로 드러납니다.",
            "rdfs:label을 한국어(@ko)와 영어(@en)로 붙입니다.",
        ))
    total = len(entities) - len(no_label)
    for rule, lang, items, why in (
        ("META02", "ko", no_ko, "한국 사용자가 쓰는 화면에서 영어나 IRI가 보입니다."),
        ("META03", "en", no_en, "해외 도구나 외부 공개 때 레이블이 비어 보입니다."),
    ):
        if items:
            report.add(Finding(
                CAT, rule, "minor", f"{len(items)}개 요소",
                f"레이블이 있는 클래스·속성 {total}개 가운데 {len(items)}개에 @{lang} 레이블이 없습니다. {why}",
                f"rdfs:label \"...\"@{lang}을 더합니다. 대상 목록은 detail.targets에 있습니다.",
                {"count": len(items), "of": total, "targets": [str(x) for x in items]},
            ))
    report.ran.append("metadata")
