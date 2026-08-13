"""열차 provider 어댑터.

각 provider 는 `TrainProvider` 인터페이스를 구현한다.
- MockProvider: 가짜 데이터 (기본, 개발/리뷰용)
- KtxProvider / SrtProvider: 실제 라이브러리 연동 (data_source=live 일 때)
"""

from app.providers.base import ProviderError, TrainProvider
from app.providers.factory import get_provider

__all__ = ["TrainProvider", "ProviderError", "get_provider"]
