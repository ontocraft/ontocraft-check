"""검사를 차례로 돌려 보고서를 만듭니다."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from rdflib.namespace import RDF

from .checks import cq as cq_check
from .checks import logic, metadata, pitfalls, registry, shacl
from .graph import LoadError, build_inventory, find_individuals, load_graph, relative_names
from .model import IGNORE_NAME_RULES, Report
from .render import RULE_TITLES

DEFAULT_GROUP_OVER = 10


def split_ids(value, upper: bool) -> list[str]:
    """쉼표로 이은 문자열이나 목록을 중복 없는 id 목록으로 바꿉니다."""
    if not value:
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    out = []
    for x in items:
        x = str(x).strip()
        x = x.upper() if upper else x
        if x and x not in out:
            out.append(x)
    return out


def run(
    ontology: str,
    data: str | None = None,
    shapes: str | None = None,
    registry_dir: str | None = None,
    reasoner: str = "rl",
    domains: list[str] | str | None = None,
    disable: list[str] | str | None = None,
    group_over: int | None = DEFAULT_GROUP_OVER,
    strict_domains: bool = False,
    cq: str | None = None,
    cq_query_field: str | None = None,
    cq_allow_labels: list[str] | str | None = None,
    cq_allow_relations: list[str] | str | None = None,
    ignore_names: list[str] | str | None = None,
    registry_match: str = "both",
    cq_format: str | None = None,
    cq_profile: str | None = None,
    cq_base: str | None = None,
) -> Report:
    """검사를 돌립니다.

    registry_dir: 등록부 폴더. "builtin" 이면 패키지에 넣은 공개 분야 사본을 씁니다. 없으면 대조하지 않습니다.
    domains: 등록부 대조에서 후보로 낼 분야 id 목록(없으면 모든 분야). 등록부에 적힌 관련 분야(related)를
        한 단계 더해 함께 봅니다. 더한 분야는 options["related_domains"] 에 적습니다.
    strict_domains: 참이면 관련 분야를 더하지 않고 domains 만 봅니다.
    disable: 끌 규칙 id 목록(예: ["P13", "P22"]). 끈 규칙의 항목은 보고서와 종료 코드에서 빠집니다.
    cq: CQ(역량 질문) JSON 파일. 주면 CQ 커버리지(report.cq, 정보 항목 CQ01)를 냅니다.
    cq_query_field: 질의 필드 이름(기본: cypher, 없으면 sparql).
    cq_allow_labels, cq_allow_relations: OWL 에 없어도 정상인 라벨·관계 타입(쉼표 문자열이나 목록, 끝의 * 와일드카드).
    ignore_names: 명명·메타데이터 규칙(P08, P22, P32, LBL01, LBL02, META02~04)에서 뺄 이름 glob(쉼표 문자열이나 목록).
        로컬 이름이나 온톨로지 IRI 아래의 상대 경로(예: ActionLog_x/status)와 맞춥니다. 다른 규칙에는 쓰지 않습니다.
    registry_match: 등록부 대조 방식. ko(한국어 레이블·로컬 이름), en(영어 이름), both(기본, 한국어가 먼저).
    cq_format: CQ 파일 형식. None·auto(items[].check 가 있으면 ontoflow), default, ontoflow.
    cq_profile: CQ 이름 대응 방식. default(라벨·영어 레이블) 또는 ontoflow(objectType·rel/·클래스/속성 IRI).
    cq_base: ontoflow 프로필의 기준 IRI 틀(예: https://ontocraft.com/ontology/{project}/). 없으면 온톨로지 IRI 입니다.
    group_over: 같은 규칙의 항목이 이 수를 넘으면 md·html 보고서에서 한 항목으로 묶습니다. 0이면 묶지 않고, None 이면 기본값(10)입니다.
    """
    domains = split_ids(domains, upper=False)
    disable = split_ids(disable, upper=True)
    ignore = split_ids(ignore_names, upper=False)
    registry_match = (registry_match or "both").strip().lower()
    if registry_match not in registry.MATCH_MODES:
        raise LoadError(f"--registry-match 는 {', '.join(registry.MATCH_MODES)} 가운데 하나입니다: {registry_match}")
    group_over = DEFAULT_GROUP_OVER if group_over is None else max(0, int(group_over))
    registry_path, registry_label = registry.resolve_registry(registry_dir)
    strict_domains = bool(strict_domains)
    related = registry.expand_domains(registry_path, domains, strict=strict_domains)
    tbox, fmt = load_graph(ontology)
    data_g = shapes_g = None
    data_fmt = shapes_fmt = None
    if data:
        data_g, data_fmt = load_graph(data)
    if shapes:
        shapes_g, shapes_fmt = load_graph(shapes)

    inv = build_inventory(tbox)
    ignore_counts = []
    for pat in ignore:
        hit = {e for e in inv.entities if any(fnmatch.fnmatchcase(n, pat) for n in relative_names(inv, str(e)))}
        inv.ignored |= hit
        ignore_counts.append({"pattern": pat, "count": len(hit),
                              "classes": len(hit & inv.classes), "properties": len(hit - inv.classes)})
    stats = {
        "classes": len(inv.classes),
        "object_properties": len(inv.object_props),
        "data_properties": len(inv.data_props),
        "annotation_properties": len(inv.annotation_props),
        "other_properties": len(inv.other_props),
        "individuals": len(inv.individuals),
        "ontology_iri": [str(o) for o in inv.ontologies],
    }
    if data_g is not None:
        stats["data_triples"] = len(data_g)
        decl = inv.classes | inv.declared_props | set(inv.ontologies)
        stats["data_individuals"] = len(find_individuals(data_g, decl) - inv.individuals)
        stats["data_typed_nodes"] = len({s for s in data_g.subjects(RDF.type, None)})
    report = Report(
        source=str(Path(ontology)),
        source_format=fmt,
        triples=len(tbox),
        stats=stats,
        inputs={
            "ontology": str(ontology),
            "data": data,
            "data_format": data_fmt,
            "shapes": shapes,
            "shapes_format": shapes_fmt,
            "registry": registry_label,
            "reasoner": reasoner,
            "cq": cq,
        },
        options={
            "domains": domains,
            "related_domains": related,
            "strict_domains": strict_domains,
            "disabled": disable,
            "unknown_disabled": [r for r in disable if r not in RULE_TITLES],
            "group_over": group_over,
            "ignore_names": ignore_counts,
            "ignore_name_rules": list(IGNORE_NAME_RULES) if ignore else [],
            "ignored_total": len(inv.ignored),
            "registry_match": registry_match,
        },
    )
    pitfalls.check(inv, report)
    metadata.check(inv, report)
    logic.check(tbox, data_g, report, reasoner=reasoner)
    shacl.check(tbox, data_g, shapes_g, report)
    registry.check(inv, registry_path, report, domains=domains or None, related=related or None,
                   match=registry_match)
    cq_check.check(inv, report, cq, query_field=cq_query_field,
                   allow_labels=cq_allow_labels, allow_relations=cq_allow_relations,
                   cq_format=cq_format, profile=cq_profile, base=cq_base)
    report.apply_disable(disable)
    return report
