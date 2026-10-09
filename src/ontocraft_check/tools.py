"""에이전트용 도구 함수입니다. MCP 서버(mcp_server.py)가 이 함수들을 그대로 감쌉니다.

mcp 패키지 없이도 쓸 수 있도록 표준 라이브러리와 이 패키지만 씁니다.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import TOOL_NAME, __version__
from .model import CATEGORIES, CATEGORY_KO, SEVERITIES, SEVERITY_KO, SEVERITY_RANK
from .render import CANNOT_SAY, render
from .rules import all_rules, rule_info
from .runner import run
from .terms import get_term as _get_term
from .terms import list_builtin_domains
from .terms import search_terms as _search_terms

FORMATS = ("summary", "json", "markdown")
TOP_N = 20
_CONTENT_HINTS = ("@prefix", "@base", "prefix ", "base ", "<", "{", "[", "#")


class InputError(ValueError):
    """입력을 파일 경로로도 본문으로도 쓸 수 없을 때 냅니다."""


def _looks_like_content(text: str) -> bool:
    if "\n" in text:
        return True
    head = text.lstrip().lower()
    return head.startswith(_CONTENT_HINTS) or " " in text.strip()


def _suffix_for(text: str) -> str:
    head = text.lstrip()[:200].lower()
    if head.startswith(("{", "[")):
        return ".jsonld"
    if head.startswith("<?xml") or "<rdf:rdf" in head:
        return ".rdf"
    return ".ttl"


def resolve_input(value: str | None, role: str, workdir: Path) -> tuple[str | None, str | None]:
    """(읽을 경로, 보고서에 적을 이름)을 돌려줍니다. 있는 파일이면 경로로, 아니면 본문으로 봅니다."""
    if value is None or str(value).strip() == "":
        return None, None
    text = str(value)
    if len(text) < 4096 and "\n" not in text:
        p = Path(text.strip()).expanduser()
        if p.is_file():
            return str(p), str(p)
        if not _looks_like_content(text):
            raise InputError(f"{role}: 파일이 없습니다: {text.strip()}")
    path = workdir / f"{role}{_suffix_for(text)}"
    path.write_text(text, encoding="utf-8")
    return str(path), f"({role} 본문 문자열, {len(text)}자)"


def summarize(report) -> dict:
    """에이전트가 읽기 좋은 짧은 요약입니다. 치명·중요 항목은 상위 TOP_N 개만 싣습니다."""
    summ = report.summary()
    ran = set(report.ran)
    counts = {}
    for cat in CATEGORIES:
        if cat == "cq" and report.cq is None:
            continue
        c = summ[cat]
        counts[CATEGORY_KO[cat]] = {
            "status": "실행" if cat in ran else "건너뜀",
            **{SEVERITY_KO[s]: c[s] for s in SEVERITIES if c[s]},
        }
    totals = {SEVERITY_KO[s]: sum(summ[cat][s] for cat in CATEGORIES) for s in SEVERITIES}
    serious = [f for f in report.findings if f.severity in ("critical", "important")]
    serious.sort(key=lambda f: -SEVERITY_RANK[f.severity])
    top = [{"rule": f.rule, "severity": SEVERITY_KO[f.severity], "category": CATEGORY_KO[f.category],
            "target": f.target, "message": f.message, "fix": f.fix} for f in serious[:TOP_N]]
    reg = [f for f in report.findings if f.category == "registry"]
    out = {
        "tool": TOOL_NAME,
        "version": __version__,
        "source": report.source,
        "triples": report.triples,
        "classes": report.stats.get("classes"),
        "properties": sum(report.stats.get(k, 0) for k in
                          ("object_properties", "data_properties", "annotation_properties", "other_properties")),
        "totals": totals,
        "by_category": counts,
        "critical_and_important": top,
        "critical_and_important_more": max(0, len(serious) - TOP_N),
        "skipped": [{"category": CATEGORY_KO[k.category], "check": k.name, "reason": k.reason} for k in report.skipped],
        "cannot_say": CANNOT_SAY,
    }
    if reg:
        out["registry_candidates"] = {
            "REG01": sum(1 for f in reg if f.rule == "REG01"),
            "REG02": sum(1 for f in reg if f.rule == "REG02"),
            "REG03": sum(1 for f in reg if f.rule == "REG03"),
            "examples": [{"target": f.target, "term_iri": f.detail.get("term_iri"),
                          "confidence": f.detail.get("confidence")} for f in reg if f.rule == "REG01"][:10],
            "note": "표기만 같은 후보입니다. get_term 으로 정의를 읽고 뜻이 같을 때만 skos:exactMatch 를 더합니다.",
        }
    if report.cq is not None:
        cq = report.cq
        out["cq_coverage"] = {
            "cq": cq["total"],
            "parsed": cq["parsed"],
            "failed": [x["id"] for x in cq["failed"]],
            "coverage": {k: {"touched": v["touched"], "total": v["total"], "ambiguous_only": v["ambiguous_only"]}
                         for k, v in cq["coverage"].items()},
            "unreached_counts": {k: len(v) for k, v in cq["unreached"].items()},
            "CQ01": len(cq["unresolved"]),
            "CQ01_examples": [{"kind": x["kind"], "name": x["name"], "cq": x["cq"][:5]} for x in cq["unresolved"][:10]],
            "notes": cq["notes"],
            "more": "요소별 표, CQ별 표, 닿지 않는 요소 목록은 format=json 의 cq 나 format=markdown 에 있습니다.",
        }
    if report.options.get("related_domains"):
        out["related_domains"] = report.options["related_domains"]
    if report.options.get("disabled"):
        out["disabled"] = report.options["disabled"]
    return out


def check_ontology(
    ontology: str,
    data: str | None = None,
    shapes: str | None = None,
    domains: list[str] | None = None,
    disable: list[str] | None = None,
    use_registry: bool = True,
    format: str = "summary",
    strict_domains: bool = False,
    cq: str | None = None,
    cq_query_field: str | None = None,
    cq_allow_labels: list[str] | None = None,
    cq_allow_relations: list[str] | None = None,
) -> dict | str:
    """온톨로지를 검사합니다. ontology·data·shapes 는 파일 경로나 본문 문자열입니다.

    format: summary(요약 사전), json(전체 보고서 사전), markdown(보고서 문자열).
    use_registry 가 참이면 내장 용어 등록부와 대조합니다.
    domains 에는 관련 분야를 한 단계 더해 봅니다. strict_domains 가 참이면 더하지 않습니다.
    cq 는 CQ JSON 파일 경로나 JSON 본문입니다. 주면 CQ 커버리지를 냅니다(summary 에 cq_coverage).
    """
    if format not in FORMATS:
        raise InputError(f"format 은 {', '.join(FORMATS)} 가운데 하나입니다: {format}")
    with tempfile.TemporaryDirectory(prefix="ontocraft-check-") as tmp:
        work = Path(tmp)
        o_path, o_label = resolve_input(ontology, "ontology", work)
        if not o_path:
            raise InputError("ontology 가 비었습니다.")
        d_path, d_label = resolve_input(data, "data", work)
        s_path, s_label = resolve_input(shapes, "shapes", work)
        c_path, c_label = resolve_input(cq, "cq", work)
        if c_path and not c_path.endswith(".json") and c_label.startswith("("):
            renamed = Path(c_path).with_suffix(".json")
            Path(c_path).rename(renamed)
            c_path = str(renamed)
        report = run(o_path, data=d_path, shapes=s_path,
                     registry_dir="builtin" if use_registry else None,
                     domains=domains or None, disable=disable or None, strict_domains=strict_domains,
                     cq=c_path, cq_query_field=cq_query_field or None,
                     cq_allow_labels=cq_allow_labels or None, cq_allow_relations=cq_allow_relations or None)
    report.source = o_label
    report.inputs.update({"ontology": o_label, "data": d_label, "shapes": s_label})
    if report.cq is not None:
        report.inputs["cq"] = c_label
        report.cq["source"] = c_label
    if format == "summary":
        return summarize(report)
    if format == "json":
        return json.loads(render(report, "json"))
    return render(report, "md")


def explain_rule(rule_id: str) -> dict:
    info = rule_info(rule_id)
    if info is None:
        raise InputError(f"없는 규칙 id 입니다: {rule_id}. list_rules 로 목록을 봅니다.")
    return info


def list_rules() -> list[dict]:
    return [{k: r[k] for k in ("rule", "title", "category_ko", "severity_ko")} for r in all_rules()]


def search_terms(query: str, domain: str | None = None, limit: int = 10) -> list[dict]:
    if domain and domain not in {d["id"] for d in list_builtin_domains()}:
        raise InputError(f"내장 등록부에 없는 분야 id 입니다: {domain}. 분야: "
                         + ", ".join(d["id"] for d in list_builtin_domains()))
    return _search_terms(query, domain=domain, limit=limit)


def get_term(id: str) -> dict:  # noqa: A002 (도구 인자 이름을 id 로 둡니다)
    t = _get_term(id)
    if t is None:
        raise InputError(f"내장 등록부에 없는 용어 id 입니다: {id}. search_terms 로 찾습니다.")
    return t
