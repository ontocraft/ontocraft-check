"""내장 용어 등록부 사본을 다시 만드는 개발용 스크립트입니다.

aki-space 저장소의 data/registry 에서 domains.json 의 status 가 published 인 분야만 골라
src/ontocraft_check/data/registry/<분야>.json 으로 옮깁니다. 용어마다 공개 필드만 남기고
seed·notes 같은 내부 필드는 뺍니다. 쓰지 않게 된 용어(status 가 active 가 아닌 것)는 넣지 않습니다.

    python3 scripts/sync_registry.py <aki-space 경로> [--date 2026-10-09]

표준 라이브러리만 씁니다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "ontocraft_check" / "data" / "registry"

REGISTRY_NAME = "OntoCraft 한국 산업 용어 등록부"
REGISTRY_EN = "OntoCraft Korean Industry Term Registry"
BASE_URI = "https://w3id.org/ontocraft/terms/"
LICENSE = "CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
TERM_FIELDS = ("id", "ko", "en", "alt", "definition", "category", "broader", "related", "refs", "example")
FILE_FIELDS = ("domain", "version", "updated", "categories")


def header(snapshot: str) -> dict:
    return {
        "registry": REGISTRY_NAME,
        "registry_en": REGISTRY_EN,
        "publisher": "OntoCraft",
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "attribution": f"출처: {REGISTRY_NAME}(OntoCraft), {LICENSE}. 용어 주소는 {BASE_URI}<id> 입니다.",
        "base_uri": BASE_URI,
        "uri_template": BASE_URI + "{id}",
        "snapshot": snapshot,
        "note": "ontocraft-check 에 넣은 공개 분야 사본입니다. 정본은 OntoCraft 가 관리하는 등록부이고, "
                "이 사본은 스냅샷 날짜 기준입니다. 내부 필드는 뺐습니다.",
    }


def clean_term(t: dict) -> dict:
    out = {}
    for k in TERM_FIELDS:
        v = t.get(k)
        if v in (None, "", []):
            continue
        out[k] = v
    return out


def build(aki_space: Path, snapshot: str, out: Path = OUT) -> dict:
    reg = aki_space / "data" / "registry"
    domains = json.loads((reg / "domains.json").read_text(encoding="utf-8"))["domains"]
    published = [d for d in domains if d.get("status") == "published"]
    if not published:
        raise SystemExit(f"공개(published) 분야가 없습니다: {reg / 'domains.json'}")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    manifest = {**header(snapshot), "domains": [], "total_terms": 0}
    seen: dict[str, str] = {}
    for d in sorted(published, key=lambda x: x.get("order", 0)):
        src = json.loads((reg / f"{d['id']}.json").read_text(encoding="utf-8"))
        terms = [clean_term(t) for t in src["terms"]
                 if isinstance(t, dict) and t.get("id") and t.get("status") in (None, "active")]
        for t in terms:
            if t["id"] in seen:
                print(f"경고: 용어 id {t['id']} 가 {seen[t['id']]} 와 {d['id']} 에 모두 있습니다", file=sys.stderr)
            seen[t["id"]] = d["id"]
        data = {**header(snapshot), **{k: src[k] for k in FILE_FIELDS if k in src}, "terms": terms}
        (out / f"{d['id']}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        dom = src.get("domain") or {"id": d["id"]}
        manifest["domains"].append({"id": dom.get("id", d["id"]), "name": dom.get("name"), "en": dom.get("en"),
                                    "file": f"{d['id']}.json", "version": src.get("version"), "terms": len(terms)})
        manifest["total_terms"] += len(terms)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="aki-space 의 공개 용어 등록부로 내장 사본을 다시 만듭니다.")
    p.add_argument("aki_space", help="aki-space 저장소 경로")
    p.add_argument("--date", default=dt.date.today().isoformat(), help="스냅샷 날짜(기본 오늘)")
    args = p.parse_args(argv)
    m = build(Path(args.aki_space).expanduser(), args.date)
    for d in m["domains"]:
        print(f"{d['id']:<14} {d['name']:<12} v{d['version']:<6} {d['terms']}개")
    print(f"합계 {len(m['domains'])}개 분야, 용어 {m['total_terms']}개, 스냅샷 {m['snapshot']} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
