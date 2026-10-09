"""검사 결과를 담는 자료 구조입니다."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

SEVERITIES = ("critical", "important", "minor", "info")
SEVERITY_KO = {"critical": "치명", "important": "중요", "minor": "경미", "info": "정보"}
SEVERITY_RANK = {"critical": 3, "important": 2, "minor": 1, "info": 0}

CATEGORIES = ("pitfall", "metadata", "logic", "shacl", "registry")
CATEGORY_KO = {
    "pitfall": "모델링 함정",
    "metadata": "메타데이터·명명",
    "logic": "논리",
    "shacl": "데이터 제약",
    "registry": "용어 등록부 대조",
}


@dataclass
class Finding:
    category: str
    rule: str
    severity: str
    target: str
    message: str
    fix: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity_ko"] = SEVERITY_KO[self.severity]
        d["category_ko"] = CATEGORY_KO[self.category]
        return d


@dataclass
class Skip:
    category: str
    name: str
    reason: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category_ko"] = CATEGORY_KO[self.category]
        return d


@dataclass
class Report:
    source: str
    source_format: str
    triples: int
    stats: dict
    inputs: dict
    findings: list[Finding] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)
    ran: list[str] = field(default_factory=list)
    # 0.2: 실행 선택지입니다. domains(고른 분야), disabled(끈 규칙), disabled_counts(끈 규칙별로 뺀 항목 수),
    # unknown_disabled(이 도구에 없는 규칙 id), group_over(보고서에서 묶는 기준, 0이면 묶지 않음)
    options: dict = field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def skip(self, category: str, name: str, reason: str) -> None:
        self.skipped.append(Skip(category, name, reason))

    def by_category(self, category: str) -> list[Finding]:
        return [f for f in self.findings if f.category == category]

    def apply_disable(self, rules) -> None:
        """끈 규칙의 항목을 뺍니다. 뺀 개수는 options 에 남깁니다."""
        off = set(rules)
        counts = {r: 0 for r in rules}
        kept = []
        for f in self.findings:
            if f.rule in off:
                counts[f.rule] += 1
            else:
                kept.append(f)
        self.findings = kept
        self.options["disabled_counts"] = counts

    def summary(self) -> dict:
        out = {}
        for cat in CATEGORIES:
            counts = {s: 0 for s in SEVERITIES}
            for f in self.by_category(cat):
                counts[f.severity] += 1
            out[cat] = counts
        return out

    def worst_at_least(self, level: str) -> bool:
        """level 이상의 심각도를 가진 항목이 있는지 봅니다. 정보 항목은 세지 않습니다."""
        if level == "none":
            return False
        need = SEVERITY_RANK[level]
        return any(
            f.severity != "info" and SEVERITY_RANK[f.severity] >= need for f in self.findings
        )
