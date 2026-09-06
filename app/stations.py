"""열차 종류별 선택 가능한 역 목록.

KTX: korail2 라이브러리는 역명을 문자열로 받아 서버에서 해석한다.
     주요 고속철도 역(경부/호남/경전/동해 등)을 수동 목록으로 관리한다.
(2026.9 KTX/SRT 통합 이후 코레일(KTX) 단일 운영사만 지원)
"""

from __future__ import annotations

from app.schemas import TrainType

# KTX 주요 역 (경부·호남·경전·동해·중앙선 등)
KTX_STATIONS: list[str] = [
    "서울",
    "용산",
    "광명",
    "수원",
    "천안아산",
    "오송",
    "대전",
    "서대전",
    "김천구미",
    "동대구",
    "경주",
    "신경주",
    "울산(통도사)",
    "포항",
    "밀양",
    "구포",
    "부산",
    "마산",
    "창원중앙",
    "창원",
    "진영",
    "진주",
    "익산",
    "정읍",
    "광주송정",
    "나주",
    "목포",
    "전주",
    "남원",
    "순천",
    "여수EXPO",
    "공주",
    "강릉",
    "만종",
    "둔내",
    "평창",
    "진부(오대산)",
    "횡성",
    "원주",
    "양평",
    "상봉",
    "청량리",
]

def get_stations(train_type: TrainType = TrainType.KTX) -> list[str]:
    """열차 종류에 맞는 역 목록 반환. (현재 KTX 단일)"""
    return KTX_STATIONS


# 열차 종류별 기본 출발역/도착역
_DEFAULTS: dict[TrainType, tuple[str, str]] = {
    TrainType.KTX: ("서울", "울산(통도사)"),
}


def get_default_stations(train_type: TrainType = TrainType.KTX) -> tuple[str, str]:
    """열차 종류에 맞는 (기본 출발역, 기본 도착역) 반환."""
    return _DEFAULTS.get(train_type, ("서울", "부산"))
