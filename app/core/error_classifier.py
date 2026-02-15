"""
에러 진단 시스템 — API 에러를 사용자 친화적 메시지로 분류

각 외부 API 호출 실패 시 에러 유형을 자동 판별하고,
사용자가 즉시 문제를 파악하고 해결할 수 있도록 안내 메시지를 생성한다.
"""
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    AUTH_EXPIRED = "auth_expired"          # 토큰/키 만료
    AUTH_INVALID = "auth_invalid"          # 키/토큰 잘못됨
    CREDITS_EXHAUSTED = "credits"          # 크레딧/잔액 부족
    RATE_LIMIT = "rate_limit"              # 요청 한도 초과
    NETWORK = "network"                    # 연결 실패/타임아웃
    SERVER = "server"                      # 외부 서버 오류
    VALIDATION = "validation"              # 입력값 문제
    NOT_CONFIGURED = "not_configured"      # API 키 미설정
    UNKNOWN = "unknown"


class DiagnosticError:
    """사용자에게 전달할 진단 정보를 담는 객체"""

    def __init__(
        self,
        error_type: ErrorType,
        service: str,
        message: str,
        action: str,
        action_link: Optional[str] = None,
        detail: Optional[str] = None,
    ):
        self.error_type = error_type
        self.service = service
        self.message = message        # 사용자에게 보여줄 한국어 메시지
        self.action = action          # 해결 방법 안내
        self.action_link = action_link  # 이동할 설정 섹션
        self.detail = detail          # 기술적 상세 (접기용)

    def to_dict(self) -> dict:
        return {
            "type": self.error_type.value,
            "service": self.service,
            "message": self.message,
            "action": self.action,
            "action_link": self.action_link,
            "detail": self.detail,
        }


# ============================================
# 서비스별 에러 분류 함수
# ============================================

def classify_gemini_error(e: Exception) -> DiagnosticError:
    """Gemini API 에러 분류"""
    msg = str(e).lower()
    status = getattr(e, "status_code", None) or getattr(e, "code", None)

    if "api_key_invalid" in msg or "api key not valid" in msg or status in (401, 403):
        return DiagnosticError(
            ErrorType.AUTH_INVALID, "Gemini",
            "Gemini API 키가 유효하지 않습니다.",
            "설정 → AI API 키에서 올바른 키를 입력하세요.",
            "/settings",
            detail=str(e)[:200],
        )
    if "resource_exhausted" in msg or "quota" in msg or status == 429:
        if "quota" in msg or "billing" in msg:
            return DiagnosticError(
                ErrorType.CREDITS_EXHAUSTED, "Gemini",
                "Gemini API 무료 할당량이 초과되었습니다.",
                "Google AI Studio에서 결제를 설정하거나 잠시 후 다시 시도하세요.",
                "/settings",
                detail=str(e)[:200],
            )
        return DiagnosticError(
            ErrorType.RATE_LIMIT, "Gemini",
            "Gemini API 요청 한도에 도달했습니다.",
            "잠시 후 다시 시도하세요. (보통 1분 이내 해제)",
            detail=str(e)[:200],
        )
    if isinstance(e, (ConnectionError, TimeoutError)) or "timeout" in msg or "connect" in msg:
        return DiagnosticError(
            ErrorType.NETWORK, "Gemini",
            "Gemini API 서버에 연결할 수 없습니다.",
            "인터넷 연결을 확인하세요.",
            detail=str(e)[:200],
        )
    if status and status >= 500:
        return DiagnosticError(
            ErrorType.SERVER, "Gemini",
            "Gemini API 서버에 일시적인 문제가 있습니다.",
            "잠시 후 다시 시도하세요.",
            detail=str(e)[:200],
        )
    return DiagnosticError(
        ErrorType.UNKNOWN, "Gemini",
        "Gemini API에서 알 수 없는 오류가 발생했습니다.",
        "에러 상세를 확인하고 다시 시도하세요.",
        detail=str(e)[:300],
    )


def classify_openai_error(e: Exception) -> DiagnosticError:
    """OpenAI API 에러 분류"""
    msg = str(e).lower()
    status = getattr(e, "status_code", None)

    if "invalid api key" in msg or "incorrect api key" in msg or status == 401:
        return DiagnosticError(
            ErrorType.AUTH_INVALID, "OpenAI",
            "OpenAI API 키가 유효하지 않습니다.",
            "설정 → AI API 키에서 올바른 키를 입력하세요.",
            "/settings",
            detail=str(e)[:200],
        )
    if "insufficient_quota" in msg or "billing" in msg or status == 402:
        return DiagnosticError(
            ErrorType.CREDITS_EXHAUSTED, "OpenAI",
            "OpenAI API 크레딧이 부족합니다.",
            "OpenAI 대시보드에서 잔액을 충전하거나 다른 AI 모델로 전환해보세요.",
            "/settings",
            detail=str(e)[:200],
        )
    if "rate_limit" in msg or status == 429:
        return DiagnosticError(
            ErrorType.RATE_LIMIT, "OpenAI",
            "OpenAI API 요청 한도에 도달했습니다.",
            "잠시 후 다시 시도하세요.",
            detail=str(e)[:200],
        )
    if isinstance(e, (ConnectionError, TimeoutError)) or "timeout" in msg:
        return DiagnosticError(
            ErrorType.NETWORK, "OpenAI",
            "OpenAI API 서버에 연결할 수 없습니다.",
            "인터넷 연결을 확인하세요.",
            detail=str(e)[:200],
        )
    return DiagnosticError(
        ErrorType.UNKNOWN, "OpenAI",
        "OpenAI API에서 오류가 발생했습니다.",
        "에러 상세를 확인하고 다시 시도하세요.",
        detail=str(e)[:300],
    )


def classify_instagram_error(e: Exception, error_data: dict = None) -> DiagnosticError:
    """Instagram Graph API 에러 분류"""
    msg = str(e).lower()
    code = None
    if error_data:
        err = error_data.get("error", {})
        code = err.get("code")
        msg = err.get("message", msg).lower()

    if code == 190 or "token" in msg and "expired" in msg:
        return DiagnosticError(
            ErrorType.AUTH_EXPIRED, "Instagram",
            "Instagram 토큰이 만료되었습니다.",
            "설정 → SNS 연결에서 토큰을 다시 발급하세요.",
            "/settings",
            detail=str(e)[:200],
        )
    if code == 10 or "permission" in msg:
        return DiagnosticError(
            ErrorType.AUTH_INVALID, "Instagram",
            "Instagram API 권한이 부족합니다.",
            "Facebook 개발자 콘솔에서 필요한 권한을 추가하세요.",
            "/settings",
            detail=str(e)[:200],
        )
    if code == 4 or "rate" in msg:
        return DiagnosticError(
            ErrorType.RATE_LIMIT, "Instagram",
            "Instagram API 요청 한도에 도달했습니다.",
            "잠시 후 다시 시도하세요. (보통 1시간 이내 해제)",
            detail=str(e)[:200],
        )
    if isinstance(e, (ConnectionError, TimeoutError)) or "timeout" in msg:
        return DiagnosticError(
            ErrorType.NETWORK, "Instagram",
            "Instagram API 서버에 연결할 수 없습니다.",
            "인터넷 연결을 확인하세요.",
            detail=str(e)[:200],
        )
    return DiagnosticError(
        ErrorType.UNKNOWN, "Instagram",
        "Instagram API에서 오류가 발생했습니다.",
        "에러 상세를 확인하고 다시 시도하세요.",
        detail=str(e)[:300],
    )


def classify_cloudinary_error(e: Exception) -> DiagnosticError:
    """Cloudinary 에러 분류"""
    msg = str(e).lower()

    if "401" in msg or "unauthorized" in msg or "invalid" in msg:
        return DiagnosticError(
            ErrorType.AUTH_INVALID, "Cloudinary",
            "Cloudinary 인증에 실패했습니다.",
            "설정 → Cloudinary에서 API Key/Secret을 확인하세요.",
            "/settings",
            detail=str(e)[:200],
        )
    if "420" in msg or "rate" in msg:
        return DiagnosticError(
            ErrorType.RATE_LIMIT, "Cloudinary",
            "Cloudinary 요청 한도에 도달했습니다.",
            "잠시 후 다시 시도하세요.",
            detail=str(e)[:200],
        )
    if isinstance(e, (ConnectionError, TimeoutError)) or "timeout" in msg:
        return DiagnosticError(
            ErrorType.NETWORK, "Cloudinary",
            "Cloudinary 서버에 연결할 수 없습니다.",
            "인터넷 연결을 확인하세요.",
            detail=str(e)[:200],
        )
    return DiagnosticError(
        ErrorType.UNKNOWN, "Cloudinary",
        "Cloudinary에서 오류가 발생했습니다.",
        "에러 상세를 확인하고 다시 시도하세요.",
        detail=str(e)[:300],
    )


def classify_general_error(e: Exception, service: str = "시스템") -> DiagnosticError:
    """일반 에러 분류 (서비스 특정 불가 시)"""
    msg = str(e).lower()

    if isinstance(e, (ConnectionError, TimeoutError)) or "timeout" in msg or "connect" in msg:
        return DiagnosticError(
            ErrorType.NETWORK, service,
            f"{service} 서버에 연결할 수 없습니다.",
            "인터넷 연결을 확인하세요.",
            detail=str(e)[:200],
        )
    return DiagnosticError(
        ErrorType.UNKNOWN, service,
        f"{service}에서 오류가 발생했습니다.",
        "에러 상세를 확인하고 다시 시도하세요.",
        detail=str(e)[:300],
    )
