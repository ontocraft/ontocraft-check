"""데이터 제약 검사입니다. pyshacl로 TBox와 데이터를 합친 그래프를 검증합니다."""

from __future__ import annotations

from rdflib import Graph
from rdflib.namespace import RDF, SH

from ..model import Finding, Report

CAT = "shacl"
SEVERITY_MAP = {SH.Violation: "critical", SH.Warning: "important", SH.Info: "minor"}
SEVERITY_NAME = {SH.Violation: "sh:Violation", SH.Warning: "sh:Warning", SH.Info: "sh:Info"}


def check(tbox: Graph, data: Graph | None, shapes: Graph | None, report: Report) -> None:
    if shapes is None or data is None:
        missing = [n for n, v in (("--shapes", shapes), ("--data", data)) if v is None]
        report.skip(CAT, "SHACL 검증", f"{'와 '.join(missing)}가 주어지지 않았습니다.")
        return
    from pyshacl import validate

    g = Graph()
    for t in tbox:
        g.add(t)
    for t in data:
        g.add(t)
    try:
        conforms, results, _ = validate(
            g, shacl_graph=shapes, inference="none", abort_on_first=False, allow_warnings=True, meta_shacl=False
        )
    except Exception as exc:
        report.skip(CAT, "SHACL 검증", f"pyshacl 실행 중 오류가 났습니다: {type(exc).__name__}: {str(exc)[:300]}")
        return

    rows = []
    for r in results.subjects(RDF.type, SH.ValidationResult):
        sev = results.value(r, SH.resultSeverity)
        focus = results.value(r, SH.focusNode)
        path = results.value(r, SH.resultPath)
        msgs = sorted(str(m) for m in results.objects(r, SH.resultMessage))
        shape = results.value(r, SH.sourceShape)
        comp = results.value(r, SH.sourceConstraintComponent)
        value = results.value(r, SH.value)
        rows.append((sev, focus, path, msgs, shape, comp, value))
    rows.sort(key=lambda x: (-_rank(x[0]), str(x[1]), str(x[2]), x[3]))
    for sev, focus, path, msgs, shape, comp, value in rows:
        path_txt = _node_text(path, shapes) if path is not None else None
        msg = "; ".join(msgs) if msgs else "(형상에 메시지가 없습니다)"
        report.add(Finding(
            CAT, "SHACL", SEVERITY_MAP.get(sev, "critical"), str(focus),
            (f"경로 {path_txt}에서 " if path_txt else "") + f"형상을 어겼습니다({SEVERITY_NAME.get(sev, str(sev))}): {msg}",
            "데이터 값을 형상 조건에 맞게 고치거나, 조건이 틀렸다면 shapes 파일의 해당 형상을 고칩니다.",
            {
                "focus_node": str(focus),
                "path": path_txt,
                "messages": msgs,
                "value": None if value is None else str(value),
                "source_shape": None if shape is None else _node_text(shape, shapes),
                "constraint": None if comp is None else str(comp).split("#")[-1],
                "shacl_severity": SEVERITY_NAME.get(sev, str(sev)),
            },
        ))
    report.stats["shacl_conforms"] = bool(conforms)
    report.stats["shacl_results"] = len(rows)
    report.stats["data_shapes"] = len(set(shapes.subjects(RDF.type, SH.NodeShape)) | set(shapes.subjects(RDF.type, SH.PropertyShape)))
    report.ran.append("shacl")


def _rank(sev) -> int:
    return {SH.Violation: 3, SH.Warning: 2, SH.Info: 1}.get(sev, 3)


def _node_text(node, g: Graph) -> str:
    from rdflib import BNode

    if isinstance(node, BNode):
        # 경로가 순서열·역경로 같은 빈 노드면 SPARQL 경로 비슷한 글로 옮깁니다.
        inv = g.value(node, SH.inversePath)
        if inv is not None:
            return "^" + _node_text(inv, g)
        return "(빈 노드)"
    try:
        return g.namespace_manager.normalizeUri(node)
    except Exception:
        return str(node)
