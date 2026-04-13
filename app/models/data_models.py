from dataclasses import dataclass
from typing import Optional


@dataclass
class HjksRecord:
    """HJKS 발전소 가동 상태 레코드 데이터 모델"""
    date: str
    region: str
    method: str
    operating_kw: float
    stopped_kw: float