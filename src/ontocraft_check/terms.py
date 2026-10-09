"""내장 용어 등록부(OntoCraft 한국 산업 용어 등록부 공개 분야 사본)에서 용어를 찾습니다.

MCP 도구 search_terms·get_term 이 씁니다. 표준 라이브러리만 씁니다.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache

from .checks.registry import BUILTIN_REGISTRY, DEFAULT_BASE, EXCLUDE, builtin_manifest


def _n(s: str) -> str:
    return unicodedata.normalize("NFC", str(s)).strip().casefold()


@lru_cache(maxsize=1)
def load_builtin() -> tuple[dict, ...]:
    """(분야 id, 분야 이름, 기준 주소, 용어) 를 담은 사전 묶음입니다."""
    out = []
    for p in sorted(BUILTIN_REGISTRY.glob("*.json")):
        if p.name in EXCLUDE:
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        dom = data.get("domain") or {}
        base = data.get("base_uri") or DEFAULT_BASE
        cats = {c.get("id"): c.get("name") for c in data.get("categories") or []}
        for t in data.get("terms") or []:
            out.append({"term": t, "domain": dom.get("id") or p.stem, "domain_name": dom.get("name") or p.stem,
                        "base": base, "category_name": cats.get(t.get("category"))})
    return tuple(out)


def _brief(rec: dict) -> dict:
    t = rec["term"]
    return {"id": t["id"], "ko": t.get("ko"), "en": t.get("en"), "definition": t.get("definition"),
            "uri": rec["base"] + t["id"], "domain": rec["domain"], "domain_name": rec["domain_name"]}


def _score(t: dict, q: str) -> tuple[int, str] | None:
    """작을수록 앞입니다. 0 표제어 일치, 1 id·영어·동의어 일치, 2 앞부분 일치, 3 부분 일치."""
    fields = [("ko", t.get("ko"))] + [("en", t.get("en")), ("id", t.get("id"))] + [("alt", a) for a in t.get("alt") or []]
    best = None
    for name, val in fields:
        if not val:
            continue
        v = _n(val)
        if v == q:
            s = 0 if name == "ko" else 1
        elif v.startswith(q):
            s = 2
        elif q in v:
            s = 3
        else:
            continue
        if best is None or s < best[0]:
            best = (s, name)
    return best


def search_terms(query: str, domain: str | None = None, limit: int = 10) -> list[dict]:
    """ko·alt·en·id 로 찾습니다. 정확히 같은 것, 앞부분이 같은 것, 들어 있는 것 순입니다."""
    q = _n(query or "")
    if not q:
        return []
    limit = max(1, min(int(limit or 10), 100))
    hits = []
    for i, rec in enumerate(load_builtin()):
        if domain and rec["domain"] != domain:
            continue
        sc = _score(rec["term"], q)
        if sc is None:
            continue
        hits.append((sc[0], len(rec["term"].get("ko") or ""), i, sc[1], rec))
    hits.sort(key=lambda x: x[:3])
    out = []
    for s, _, _, field, rec in hits[:limit]:
        b = _brief(rec)
        b["matched_field"] = field
        b["match"] = ("exact" if s <= 1 else "prefix" if s == 2 else "contains")
        out.append(b)
    return out


def get_term(term_id: str) -> dict | None:
    """id 로 용어 하나를 모든 공개 필드와 함께 돌려줍니다. 없으면 None 입니다."""
    tid = (term_id or "").strip()
    if tid.startswith(DEFAULT_BASE):
        tid = tid[len(DEFAULT_BASE):]
    for rec in load_builtin():
        if rec["term"]["id"] == tid:
            out = {**rec["term"], "uri": rec["base"] + tid, "domain": rec["domain"],
                   "domain_name": rec["domain_name"], "category_name": rec["category_name"]}
            m = builtin_manifest()
            out["source"] = {"registry": m.get("registry"), "license": m.get("license"),
                             "license_url": m.get("license_url"), "snapshot": m.get("snapshot")}
            return out
    return None


def list_builtin_domains() -> list[dict]:
    return builtin_manifest().get("domains", [])
