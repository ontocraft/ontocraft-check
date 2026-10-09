"""분야 사이의 관련 분야 기본표입니다. 표준 라이브러리도 쓰지 않습니다.

--domains 로 고른 분야에 관련 분야를 한 단계만 더합니다(관련의 관련은 더하지 않음).
scripts/sync_registry.py 가 aki-space domains.json 에 related 가 없을 때 이 표를 manifest.json 에 옮기고,
등록부 폴더에 related 정보가 없을 때 검사기도 이 표를 씁니다.
"""

from __future__ import annotations

# 양방향으로 씁니다. 근거가 약한 짝(예: smartcity 와 port)은 넣지 않습니다.
RELATED_PAIRS: tuple[tuple[str, str], ...] = (
    ("maritime", "port"),        # 정박지·선석·적하·양하·항만시설
    ("maint", "mfg-ai"),         # 예지보전·설비 데이터
    ("mfg-ai", "semiconductor"),  # 팹 공정 데이터·수율
    ("mfg-ai", "physical-ai"),   # 로봇·셀 자동화
    ("defense", "maritime"),     # 함정·조선
)


def default_related() -> dict[str, list[str]]:
    """분야 id -> 관련 분야 id 목록(정렬)입니다."""
    out: dict[str, set[str]] = {}
    for a, b in RELATED_PAIRS:
        out.setdefault(a, set()).add(b)
        out.setdefault(b, set()).add(a)
    return {k: sorted(v) for k, v in sorted(out.items())}
