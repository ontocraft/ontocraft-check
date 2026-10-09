from pathlib import Path

from ontocraft_check.runner import run

FIX = Path(__file__).parent / "fixtures"


def f(name: str) -> str:
    return str(FIX / name)


def local(iri: str) -> str:
    return iri.split("#")[-1]


def rules_and_targets(report, category=None):
    return {
        (x.rule, local(x.target))
        for x in report.findings
        if category is None or x.category == category
    }


__all__ = ["run", "f", "local", "rules_and_targets"]
