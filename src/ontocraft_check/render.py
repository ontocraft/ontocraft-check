"""보고서를 Markdown, HTML, JSON으로 냅니다.

세 형식이 같은 내용을 담도록, 먼저 블록 목록(제목·문단·표)을 만들고 형식별로 옮깁니다.
"""

from __future__ import annotations

import html
import json
from collections import OrderedDict

from . import TOOL_NAME, TOOL_TITLE, __version__
from .checks.logic import LIMIT_NOTE
from .model import CATEGORIES, CATEGORY_KO, SEVERITIES, SEVERITY_KO, Report

OOPS_NOTE = (
    "모델링 함정 절에서 OOPS! 함정 번호(Pxx)를 쓰는 규칙은 OOPS! Pxx의 정의를 따라 다시 구현한 근사 검사이며 "
    "OOPS! 자체의 결과가 아닙니다. OOPS! 코드는 보지도 옮기지도 않았고, 공개 함정 목록"
    "(https://oops.linkeddata.es/catalogue.jsp)의 설명 수준만 참고했습니다. "
    "DT01, LBL01, LBL02는 OOPS! 번호가 아닌 이 도구의 규칙입니다."
)

RULE_TITLES = OrderedDict([
    ("P04", "어디에도 연결되지 않은 클래스·속성"),
    ("P06", "rdfs:subClassOf 순환"),
    ("P08", "정의(rdfs:comment·skos:definition) 없음"),
    ("P10", "서로소 공리 없음"),
    ("P11", "도메인·레인지 누락"),
    ("P13", "역관계(owl:inverseOf) 없음"),
    ("P19", "도메인·레인지가 둘 이상"),
    ("P22", "클래스 이름 표기법 불일치"),
    ("P32", "같은 레이블을 가진 클래스"),
    ("LBL01", "종류가 다른 요소의 같은 레이블"),
    ("LBL02", "같은 레이블을 가진 객체 속성"),
    ("P34", "선언되지 않은 클래스"),
    ("P35", "선언되지 않은 속성"),
    ("P34-EXT", "외부 어휘 선언 없음(클래스)"),
    ("P35-EXT", "외부 어휘 선언 없음(속성)"),
    ("DT01", "선언되지 않은 데이터 타입"),
    ("P38", "owl:Ontology 선언 없음"),
    ("P41", "라이선스 없음"),
    ("META01", "버전 정보 없음"),
    ("META02", "한국어 레이블(@ko) 없음"),
    ("META03", "영어 레이블(@en) 없음"),
    ("META04", "레이블 없음"),
    ("LOGIC01", "owl:Nothing에 속한 개체"),
    ("LOGIC02", "서로소 클래스 둘에 동시에 속한 개체"),
    ("LOGIC03", "owl:sameAs와 owl:differentFrom 충돌"),
    ("LOGIC04", "그 밖의 OWL 2 RL 모순(owlrl 보고)"),
    ("LOGIC05", "HermiT 만족불가 판정"),
    ("SHACL", "형상 위반"),
    ("REG01", "등록부 skos:exactMatch 후보"),
    ("REG02", "다른 분야에서 같은 이름이 있음(뜻이 다를 수 있음)"),
    ("REG03", "속성 이름이 개념 용어와 같음"),
])

CANNOT_SAY = [
    "의미 판단이 필요한 함정은 검사하지 않았습니다. 예를 들어 P01(한 클래스에 여러 뜻), P05(잘못된 역관계), "
    "P31(잘못된 동치 관계)은 사람이 정의를 읽어야 가립니다.",
    LIMIT_NOTE + " 이 보고서에서 논리 모순이 없다는 것은 OWL 2 DL 로도 일관하다는 뜻이 아닙니다.",
    "모델링 함정과 메타데이터 검사는 온톨로지 파일 하나만 봅니다. owl:imports를 따라가지 않고, --data의 데이터 그래프도 보지 않습니다.",
    "함정 검사는 OOPS! 정의를 다시 구현한 근사 검사라서 OOPS!가 내는 결과와 개수가 다르기도 합니다.",
    "SHACL 검증은 형상 파일이 표현한 조건만큼만 말합니다. 형상이 없는 클래스와 속성의 데이터는 검사하지 않았습니다.",
    "용어 등록부 대조는 표기가 같은지만 봅니다. 뜻이 같은지는 정의를 읽고 사람이 판단해야 합니다. "
    "일치 신뢰도 「높음」도 표제어와 표기가 같다는 뜻일 뿐 뜻이 같다는 보증이 아닙니다.",
    "사용자가 끈 규칙은 검사 결과에서 뺐습니다. 끈 규칙에 해당하는 문제가 없다는 뜻이 아닙니다.",
]


def _rule_title(rule: str) -> str:
    return RULE_TITLES.get(rule, rule)


def _group_over(report: Report) -> int:
    return int(report.options.get("group_over", 0) or 0)


def rule_groups(report: Report, category: str | None = None) -> "OrderedDict[str, list]":
    """규칙 id -> 항목 목록입니다. RULE_TITLES 순서로 늘어놓습니다."""
    groups = OrderedDict()
    for f in report.findings:
        if category is None or f.category == category:
            groups.setdefault(f.rule, []).append(f)
    order = list(RULE_TITLES)
    keys = sorted(groups, key=lambda r: order.index(r) if r in order else 999)
    return OrderedDict((k, groups[k]) for k in keys)


def _same(values) -> bool:
    return len(set(values)) == 1


def _group_items(fs) -> list[str]:
    """묶은 항목의 대상 목록입니다. 설명이 대상마다 다르면 설명을 함께 적습니다."""
    if _same(f.message for f in fs):
        return [f.target for f in fs]
    return [f"{f.target}: {f.message}" for f in fs]


def grouped_summary(report: Report) -> list[dict]:
    """JSON 에 더하는 묶음 요약입니다. findings 는 그대로 두고 이 목록만 따로 둡니다."""
    limit = _group_over(report)
    if limit <= 0:
        return []
    out = []
    for rule, fs in rule_groups(report).items():
        if len(fs) <= limit:
            continue
        out.append({
            "rule": rule,
            "title": _rule_title(rule),
            "category": fs[0].category,
            "severity": fs[0].severity if _same(f.severity for f in fs) else "mixed",
            "count": len(fs),
            "message": fs[0].message if _same(f.message for f in fs) else None,
            "fix": fs[0].fix if _same(f.fix for f in fs) else None,
            "targets": [f.target for f in fs],
        })
    return out


def _disabled_text(report: Report) -> str | None:
    off = report.options.get("disabled") or []
    if not off:
        return None
    counts = report.options.get("disabled_counts", {})
    unknown = set(report.options.get("unknown_disabled") or [])
    parts = []
    for r in off:
        if r in unknown:
            continue
        parts.append(f"{r} {_rule_title(r)}(뺀 항목 {counts.get(r, 0)}건)")
    text = ""
    if parts:
        text = "사용자가 끈 규칙: " + ", ".join(parts) + ". 이 규칙의 항목은 결과 요약, 본문, 종료 코드에서 뺐습니다."
    if unknown:
        text += (" " if text else "") + "끄라고 했지만 이 도구에 없는 규칙 id입니다: " + ", ".join(sorted(unknown)) + "."
    return text


REG03_NOTE = "관계 이름은 동사구로, 개념과의 연결은 range 클래스에서 하기를 권합니다."


def _related_text(report: Report) -> str | None:
    rel = report.options.get("related_domains") or []
    if not rel:
        return None
    return ("관련 분야로 함께 봄: " + ", ".join(rel) + ". 고른 분야(" + ", ".join(report.options.get("domains") or [])
            + ")와 가까운 분야라 등록부 대조 후보에 더했습니다. 빼려면 --strict-domains를 줍니다.")


def build_blocks(report: Report) -> list:
    b = []
    b.append(("h1", f"{TOOL_TITLE} 보고서"))
    b.append(("p", f"이 보고서는 {TOOL_NAME} {__version__}으로 만들었습니다. {OOPS_NOTE}"))
    off_text = _disabled_text(report)
    if off_text:
        b.append(("p", off_text))
    rel_text = _related_text(report)
    if rel_text:
        b.append(("p", rel_text))

    s = report.stats
    b.append(("h2", "1. 입력과 규모"))
    rows = [
        ["온톨로지 파일", report.source],
        ["읽은 형식", report.source_format],
        ["온톨로지 IRI", ", ".join(s.get("ontology_iri") or []) or "(없음)"],
        ["트리플 수", str(report.triples)],
        ["클래스", str(s["classes"])],
        ["객체 속성", str(s["object_properties"])],
        ["데이터 속성", str(s["data_properties"])],
        ["주석 속성", str(s["annotation_properties"])],
        ["그 밖의 속성(rdf:Property)", str(s["other_properties"])],
        ["개체(온톨로지 파일 안)", str(s["individuals"])],
    ]
    if report.inputs.get("data"):
        rows += [
            ["데이터 파일", report.inputs["data"]],
            ["데이터 트리플 수", str(s.get("data_triples", 0))],
            ["데이터 개체", str(s.get("data_individuals", 0))],
        ]
    if report.inputs.get("shapes"):
        rows.append(["형상 파일", report.inputs["shapes"]])
    if report.inputs.get("registry"):
        rows.append(["용어 등록부", report.inputs["registry"]])
    if report.inputs.get("registry"):
        rows.append(["고른 분야", ", ".join(report.options.get("domains") or []) or "(모든 분야)"])
        if report.options.get("related_domains"):
            rows.append(["관련 분야로 함께 봄", ", ".join(report.options["related_domains"])])
        elif report.options.get("strict_domains") and report.options.get("domains"):
            rows.append(["관련 분야로 함께 봄", "(더하지 않음, --strict-domains)"])
    if "disjoint_axioms" in s:
        rows.append(["서로소 공리 수", str(s["disjoint_axioms"])])
    rows.append(["사용자가 끈 규칙", ", ".join(report.options.get("disabled") or []) or "(없음)"])
    limit = _group_over(report)
    rows.append(["항목 묶기", f"같은 규칙의 항목이 {limit}개를 넘으면 한 항목으로 묶습니다" if limit else "묶지 않습니다"])
    b.append(("table", ["항목", "값"], rows))

    b.append(("h2", "2. 결과 요약"))
    summ = report.summary()
    rows = []
    for cat in CATEGORIES:
        status = "실행" if _ran(report, cat) else "건너뜀"
        c = summ[cat]
        rows.append([CATEGORY_KO[cat], status] + [str(c[sev]) for sev in SEVERITIES])
    b.append(("table", ["검사 종류", "상태"] + [SEVERITY_KO[sv] for sv in SEVERITIES], rows))
    if report.skipped:
        b.append(("p", "건너뛴 검사와 이유는 다음과 같습니다."))
        b.append(("table", ["검사 종류", "검사", "이유"],
                  [[CATEGORY_KO[k.category], k.name, k.reason] for k in report.skipped]))
    else:
        b.append(("p", "건너뛴 검사가 없습니다."))

    for n, cat in enumerate(CATEGORIES, start=3):
        b.append(("h2", f"{n}. {CATEGORY_KO[cat]}"))
        if cat == "pitfall":
            b.append(("p", OOPS_NOTE + " 검사 범위는 온톨로지 파일입니다."))
        if cat == "logic":
            b.append(("p", "owlrl로 TBox와 데이터에 OWL 2 RL 규칙 폐포를 만든 뒤 모순을 찾았습니다. " + LIMIT_NOTE))
        if cat == "shacl" and _ran(report, cat):
            b.append(("p", "TBox와 데이터를 합친 그래프를 pyshacl로 검증했습니다(추가 추론 없음). "
                           "심각도는 형상의 sh:resultSeverity를 따릅니다. sh:Violation은 치명, sh:Warning은 중요, sh:Info는 경미입니다."))
        if cat == "registry" and _ran(report, cat):
            b.append(("p", "등록부 파일: " + ", ".join(s.get("registry_files", [])) + ". 정보 항목이며 심각도가 없습니다."))
            b.append(("p", "후보마다 등록부 분야를 적습니다. 일치 신뢰도는 표제어(ko)와 같으면 높음, 동의어(alt)로만 맞으면 "
                           "낮음입니다. 낮음은 동의어로 맞은 것이라 상위·하위 개념일 수 있으니 넣기 전에 정의를 꼭 읽습니다."))
            sel = report.options.get("domains") or []
            rel = report.options.get("related_domains") or []
            if sel and rel:
                b.append(("p", "고른 분야는 " + ", ".join(sel) + "이고, 관련 분야 " + ", ".join(rel) + "를 함께 봤습니다. "
                               "이 분야들의 용어만 REG01 후보로 냈고, 다른 분야와만 표기가 같은 것은 REG02로 따로 묶었습니다. "
                               "관련 분야를 빼려면 --strict-domains를 줍니다."))
            elif sel:
                b.append(("p", "고른 분야는 " + ", ".join(sel) + "입니다. 이 분야의 용어만 REG01 후보로 냈고, "
                               "다른 분야와만 표기가 같은 것은 REG02로 따로 묶었습니다."))
            else:
                b.append(("p", "분야를 고르지 않아 모든 분야의 용어와 대조했습니다. --domains로 분야를 고르면 "
                               "다른 분야와만 맞는 것을 따로 묶습니다."))
            b.append(("p", "REG01 후보는 클래스만 냅니다. 등록부 용어는 대부분 개념이라, 객체·데이터 속성이 개념 용어와 "
                           "표기가 같으면 REG03으로 따로 적습니다. " + REG03_NOTE))
            unknown = s.get("registry_unknown_domains") or []
            if unknown:
                b.append(("p", "등록부에 없는 분야 id입니다: " + ", ".join(unknown) + "."))
        skipped = [k for k in report.skipped if k.category == cat]
        for k in skipped:
            b.append(("p", f"건너뜀: {k.name}. {k.reason}"))
        items = report.by_category(cat)
        if not items:
            if _ran(report, cat):
                b.append(("p", "찾은 항목이 없습니다."))
            continue
        for rule, fs in rule_groups(report, cat).items():
            sev = SEVERITY_KO[fs[0].severity] if _same(f.severity for f in fs) else "여러 심각도"
            b.append(("h3", f"{rule} {_rule_title(rule)} ({sev}, {len(fs)}건)"))
            head = ["심각도", "규칙", "대상", "설명", "고치는 방법"]
            if limit and len(fs) > limit:
                msg = fs[0].message if _same(f.message for f in fs) else (
                    f"{rule} 항목이 {len(fs)}개입니다. 대상마다 설명이 달라 대상 목록에 함께 적었습니다.")
                fix = fs[0].fix if _same(f.fix for f in fs) else fs[0].fix + " 대상마다 조금씩 다르니 대상 목록을 봅니다."
                b.append(("table", head, [[sev, rule, f"{len(fs)}개 요소", msg, fix]]))
                b.append(("details", f"대상 {len(fs)}개 보기", _group_items(fs)))
            else:
                b.append(("table", head, [[SEVERITY_KO[f.severity], f.rule, f.target, f.message, f.fix] for f in fs]))

    b.append(("h2", f"{len(CATEGORIES) + 3}. 이 보고서로 말할 수 없는 것"))
    b.append(("ul", CANNOT_SAY))
    return b


def _ran(report: Report, cat: str) -> bool:
    return cat in report.ran


def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(report: Report) -> str:
    out = []
    for blk in build_blocks(report):
        kind = blk[0]
        if kind == "h1":
            out.append(f"# {blk[1]}\n")
        elif kind == "h2":
            out.append(f"## {blk[1]}\n")
        elif kind == "h3":
            out.append(f"### {blk[1]}\n")
        elif kind == "p":
            out.append(blk[1] + "\n")
        elif kind == "ul":
            out.append("\n".join(f"- {x}" for x in blk[1]) + "\n")
        elif kind == "details":
            items = "\n".join(f"- {_md_cell(x)}" for x in blk[2])
            out.append(f"<details><summary>{html.escape(blk[1])}</summary>\n\n{items}\n\n</details>\n")
        elif kind == "table":
            head, rows = blk[1], blk[2]
            lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            lines += ["| " + " | ".join(_md_cell(c) for c in r) + " |" for r in rows]
            out.append("\n".join(lines) + "\n")
    return "\n".join(out)


CSS = """
body{font-family:-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.6;color:#1f2328}
table{border-collapse:collapse;width:100%;margin:.5rem 0 1.2rem;font-size:.9rem}
th,td{border:1px solid #d0d7de;padding:.35rem .5rem;text-align:left;vertical-align:top;word-break:break-all}
th{background:#f6f8fa}
details{margin:-.6rem 0 1.2rem;font-size:.9rem}summary{cursor:pointer}
h2{border-bottom:1px solid #d0d7de;padding-bottom:.2rem;margin-top:2rem}
@media (prefers-color-scheme: dark){body{background:#0d1117;color:#e6edf3}th{background:#161b22}th,td{border-color:#30363d}}
"""


def to_html(report: Report) -> str:
    e = html.escape
    out = ["<!doctype html>", '<html lang="ko"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f"<title>{TOOL_NAME} 보고서: {e(report.source)}</title><style>{CSS}</style></head><body>"]
    for blk in build_blocks(report):
        kind = blk[0]
        if kind in ("h1", "h2", "h3"):
            out.append(f"<{kind}>{e(blk[1])}</{kind}>")
        elif kind == "p":
            out.append(f"<p>{e(blk[1])}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in blk[1]) + "</ul>")
        elif kind == "details":
            out.append(f"<details><summary>{e(blk[1])}</summary><ul>"
                       + "".join(f"<li>{e(x)}</li>" for x in blk[2]) + "</ul></details>")
        elif kind == "table":
            head, rows = blk[1], blk[2]
            t = ["<table><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr></thead><tbody>"]
            t += ["<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows]
            t.append("</tbody></table>")
            out.append("".join(t))
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def to_dict(report: Report) -> dict:
    return {
        "tool": TOOL_NAME,
        "version": __version__,
        "notice": OOPS_NOTE,
        "logic_limit": LIMIT_NOTE,
        "input": report.inputs,
        "options": report.options,
        "source": report.source,
        "source_format": report.source_format,
        "triples": report.triples,
        "stats": report.stats,
        "summary": {
            cat: {"name": CATEGORY_KO[cat], "status": "ran" if _ran(report, cat) else "skipped", **report.summary()[cat]}
            for cat in CATEGORIES
        },
        "skipped": [k.to_dict() for k in report.skipped],
        "rules": {k: v for k, v in RULE_TITLES.items()},
        "findings": [f.to_dict() for f in report.findings],
        "grouped": grouped_summary(report),
        "cannot_say": CANNOT_SAY,
    }


def to_json(report: Report) -> str:
    return json.dumps(to_dict(report), ensure_ascii=False, indent=2) + "\n"


def render(report: Report, fmt: str) -> str:
    return {"md": to_markdown, "html": to_html, "json": to_json}[fmt](report)
