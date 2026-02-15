"""
SNS 인증·연결 관리 API

- .env 파일의 SNS 관련 키 읽기/쓰기
- Facebook OAuth → Instagram/Threads 토큰 교환
- 연결 상태 확인
"""
import os
import logging
import httpx
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sns", tags=["sns-auth"])

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
GRAPH_API = "https://graph.facebook.com/v21.0"


# =============================================
# .env 파일 유틸
# =============================================

def _read_env() -> dict:
    """현재 .env 파일을 dict로 읽기"""
    result = {}
    if not os.path.exists(ENV_PATH):
        return result
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                result[key.strip()] = val.strip()
    return result


def _update_env(updates: dict):
    """기존 .env 파일의 키를 업데이트 (없으면 추가)"""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # 아직 추가되지 않은 키 추가
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # 환경변수에도 즉시 반영 (현재 프로세스)
    for key, val in updates.items():
        os.environ[key] = val

    # config 캐시 초기화
    try:
        from app.core.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass


def _mask_token(token: str) -> str:
    """토큰을 마스킹하여 표시 (앞 6 + 뒤 4만)"""
    if not token or len(token) < 15:
        return "***"
    return token[:6] + "..." + token[-4:]


# =============================================
# 상태 확인 API
# =============================================

@router.get("/status")
async def get_status():
    """모든 SNS/API 연결 상태 조회 (토큰은 마스킹)"""
    env = _read_env()

    insta_token = env.get("INSTAGRAM_ACCESS_TOKEN", "")
    insta_id = env.get("INSTAGRAM_USER_ID", "")
    cloud_name = env.get("CLOUDINARY_CLOUD_NAME", "")
    cloud_key = env.get("CLOUDINARY_API_KEY", "")
    cloud_secret = env.get("CLOUDINARY_API_SECRET", "")
    return {
        "instagram": {
            "configured": bool(insta_token and insta_id),
            "token_preview": _mask_token(insta_token),
            "user_id": insta_id,
        },
        "cloudinary": {
            "configured": bool(cloud_name and cloud_key and cloud_secret),
            "cloud_name": cloud_name,
            "api_key_preview": _mask_token(cloud_key) if cloud_key else "",
            "api_secret_preview": _mask_token(cloud_secret) if cloud_secret else "",
        },
        "facebook_app": {
            "app_id": env.get("FACEBOOK_APP_ID", ""),
            "has_secret": bool(env.get("FACEBOOK_APP_SECRET", "")),
        }
    }


@router.get("/instagram/verify")
async def verify_instagram():
    """Instagram 토큰 유효성 + 계정 정보 확인"""
    env = _read_env()
    token = env.get("INSTAGRAM_ACCESS_TOKEN", "")
    user_id = env.get("INSTAGRAM_USER_ID", "")

    if not token:
        return {"ok": False, "error": "토큰 미설정"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # 토큰 디버그
            r1 = await client.get(f"{GRAPH_API}/debug_token",
                                  params={"input_token": token, "access_token": token})
            d1 = r1.json().get("data", {})
            is_valid = d1.get("is_valid", False)
            token_type = d1.get("type", "?")
            expires_at = d1.get("expires_at", -1)
            scopes = d1.get("scopes", [])

            if not is_valid:
                return {"ok": False, "error": "토큰 만료 또는 무효", "token_type": token_type}

            # Instagram 계정 정보
            ig_info = {}
            if user_id:
                r2 = await client.get(f"{GRAPH_API}/{user_id}",
                                      params={"fields": "id,username,name,profile_picture_url",
                                              "access_token": token})
                if r2.status_code == 200:
                    ig_info = r2.json()

            return {
                "ok": True,
                "token_type": token_type,
                "expires_at": expires_at,
                "permanent": expires_at == 0,
                "scopes": scopes,
                "username": ig_info.get("username", ""),
                "name": ig_info.get("name", ""),
                "profile_picture": ig_info.get("profile_picture_url", ""),
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/cloudinary/verify")
async def verify_cloudinary():
    """Cloudinary 연결 확인"""
    env = _read_env()
    name = env.get("CLOUDINARY_CLOUD_NAME", "")
    key = env.get("CLOUDINARY_API_KEY", "")
    secret = env.get("CLOUDINARY_API_SECRET", "")
    if not all([name, key, secret]):
        return {"ok": False, "error": "Cloudinary 설정 미완료"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://api.cloudinary.com/v1_1/{name}/resources/image",
                auth=(key, secret),
                params={"max_results": 1}
            )
            if r.status_code == 200:
                return {"ok": True, "cloud_name": name}
            return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =============================================
# Facebook App 설정 저장
# =============================================

class FacebookAppConfig(BaseModel):
    app_id: str
    app_secret: str

@router.post("/facebook/save-app")
async def save_facebook_app(config: FacebookAppConfig):
    """Facebook App ID/Secret 저장"""
    if not config.app_id or not config.app_secret:
        return {"ok": False, "error": "App ID와 App Secret을 모두 입력해주세요."}
    _update_env({
        "FACEBOOK_APP_ID": config.app_id.strip(),
        "FACEBOOK_APP_SECRET": config.app_secret.strip()
    })
    return {"ok": True}


# =============================================
# Cloudinary 설정 저장
# =============================================

class CloudinaryConfig(BaseModel):
    cloud_name: str
    api_key: str = ""
    api_secret: str = ""

@router.post("/cloudinary/save")
async def save_cloudinary(config: CloudinaryConfig):
    """Cloudinary 설정 저장 (key/secret이 비어있으면 기존 값 유지)"""
    updates = {"CLOUDINARY_CLOUD_NAME": config.cloud_name.strip()}
    if config.api_key.strip():
        updates["CLOUDINARY_API_KEY"] = config.api_key.strip()
    if config.api_secret.strip():
        updates["CLOUDINARY_API_SECRET"] = config.api_secret.strip()
    _update_env(updates)
    return {"ok": True}


# =============================================
# Facebook OAuth → 토큰 교환 플로우
# =============================================

@router.get("/facebook/auth-url")
async def get_facebook_auth_url():
    """Facebook OAuth 인증 URL 생성"""
    env = _read_env()
    app_id = env.get("FACEBOOK_APP_ID", "")
    if not app_id:
        return {"ok": False, "error": "먼저 Facebook App ID를 설정해주세요."}

    redirect_uri = "https://localhost:8000/api/sns/facebook/callback"
    scopes = ",".join([
        "pages_show_list",
        "pages_read_engagement",
        "instagram_basic",
        "instagram_content_publish",
        "business_management",
    ])
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&response_type=code"
    )
    return {"ok": True, "url": auth_url}


class TokenExchangeRequest(BaseModel):
    short_token: str

@router.post("/facebook/exchange-token")
async def exchange_token(request: TokenExchangeRequest):
    """단기 토큰 → 장기 → 영구 페이지 토큰 자동 교환 + .env 저장"""
    env = _read_env()
    app_id = env.get("FACEBOOK_APP_ID", "")
    app_secret = env.get("FACEBOOK_APP_SECRET", "")

    if not app_id or not app_secret:
        return {"ok": False, "error": "Facebook App ID/Secret이 설정되지 않았습니다.", "step": 0}

    short_token = request.short_token.strip()
    if not short_token:
        return {"ok": False, "error": "토큰을 입력해주세요.", "step": 0}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: 단기 → 장기 사용자 토큰
            r1 = await client.get(f"{GRAPH_API}/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            })
            d1 = r1.json()
            if "access_token" not in d1:
                err = d1.get("error", {}).get("message", str(d1))
                return {"ok": False, "error": f"장기 토큰 교환 실패: {err}", "step": 1}

            long_token = d1["access_token"]
            expires_in = d1.get("expires_in", 0)
            logger.info(f"[SNS Auth] 장기 사용자 토큰 발급 (만료: {expires_in}초)")

            # Step 2: 페이지 목록 + Instagram 비즈니스 계정 조회
            r2 = await client.get(f"{GRAPH_API}/me/accounts", params={
                "fields": "id,name,access_token,instagram_business_account",
                "access_token": long_token,
            })
            pages = r2.json().get("data", [])

            if not pages:
                # 페이지 없으면 장기 사용자 토큰만 저장
                _update_env({"INSTAGRAM_ACCESS_TOKEN": long_token})
                return {
                    "ok": True,
                    "step": 2,
                    "token_type": "user",
                    "permanent": False,
                    "expires_days": expires_in // 86400,
                    "message": "페이지가 없어 장기 사용자 토큰(60일)을 저장했습니다.",
                    "pages": []
                }

            # Instagram 연결된 페이지 찾기
            ig_page = None
            for p in pages:
                if p.get("instagram_business_account", {}).get("id"):
                    ig_page = p
                    break

            if not ig_page:
                # Instagram 없는 페이지의 첫 번째 페이지 토큰 사용
                ig_page = pages[0]

            page_token = ig_page["access_token"]
            ig_id = ig_page.get("instagram_business_account", {}).get("id", "")

            # Step 3: 페이지 토큰 검증 (영구인지 확인)
            r3 = await client.get(f"{GRAPH_API}/debug_token", params={
                "input_token": page_token,
                "access_token": page_token,
            })
            d3 = r3.json().get("data", {})
            is_permanent = d3.get("expires_at", -1) == 0

            # Step 4: Instagram 계정 정보 조회
            ig_username = ""
            ig_profile_pic = ""
            if ig_id:
                r4 = await client.get(f"{GRAPH_API}/{ig_id}", params={
                    "fields": "id,username,name,profile_picture_url",
                    "access_token": page_token,
                })
                if r4.status_code == 200:
                    ig_data = r4.json()
                    ig_username = ig_data.get("username", "")
                    ig_profile_pic = ig_data.get("profile_picture_url", "")

            # .env에 저장
            updates = {"INSTAGRAM_ACCESS_TOKEN": page_token}
            if ig_id:
                updates["INSTAGRAM_USER_ID"] = ig_id
            _update_env(updates)

            logger.info(f"[SNS Auth] 영구 페이지 토큰 저장 완료 (ig: @{ig_username})")

            return {
                "ok": True,
                "step": 3,
                "token_type": "page",
                "permanent": is_permanent,
                "page_name": ig_page.get("name", ""),
                "instagram_user_id": ig_id,
                "instagram_username": ig_username,
                "instagram_profile_pic": ig_profile_pic,
                "message": f"{'영구' if is_permanent else '장기'} 토큰 발급 & 저장 완료!",
                "pages": [
                    {
                        "name": p["name"],
                        "page_id": p["id"],
                        "has_instagram": bool(p.get("instagram_business_account", {}).get("id")),
                        "ig_id": p.get("instagram_business_account", {}).get("id", ""),
                    }
                    for p in pages
                ]
            }

    except Exception as e:
        logger.error(f"[SNS Auth] 토큰 교환 오류: {e}")
        return {"ok": False, "error": str(e), "step": -1}


class DirectTokenSave(BaseModel):
    token: str
    user_id: str = ""

@router.post("/instagram/save-direct")
async def save_instagram_direct(body: DirectTokenSave):
    """Instagram 토큰을 직접 입력하여 저장"""
    if not body.token.strip():
        return {"ok": False, "error": "토큰을 입력해주세요."}
    updates = {"INSTAGRAM_ACCESS_TOKEN": body.token.strip()}
    if body.user_id.strip():
        updates["INSTAGRAM_USER_ID"] = body.user_id.strip()
    _update_env(updates)
    return {"ok": True}


# =============================================
# AI API 키 관리
# =============================================

class ApiKeySave(BaseModel):
    key: str
    value: str

@router.post("/apikey/save")
async def save_api_key(body: ApiKeySave):
    """개별 API 키를 .env에 저장"""
    allowed = {"GEMINI_API_KEY"}
    if body.key not in allowed:
        return {"ok": False, "error": f"허용되지 않은 키: {body.key}"}
    if not body.value.strip():
        return {"ok": False, "error": "값을 입력해주세요."}
    _update_env({body.key: body.value.strip()})
    return {"ok": True}


@router.get("/apikey/status")
async def api_key_status():
    """AI API 키 설정 상태 확인 (마스킹)"""
    env = _read_env()
    gemini = env.get("GEMINI_API_KEY", "")
    return {
        "gemini": {"configured": bool(gemini), "preview": _mask_token(gemini)},
    }


@router.get("/apikey/verify/gemini")
async def verify_gemini():
    """Gemini API 키 유효성 확인"""
    env = _read_env()
    key = env.get("GEMINI_API_KEY", "")
    if not key:
        return {"ok": False, "error": "미설정"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            )
            if r.status_code == 200:
                models = r.json().get("models", [])
                return {"ok": True, "models": len(models)}
            return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/system/status")
async def system_status():
    """전체 API 연결 상태 요약 (헤더 상태 바용)"""
    env = _read_env()
    result = {}

    # Gemini
    gemini_key = env.get("GEMINI_API_KEY", "")
    if gemini_key and len(gemini_key) > 10:
        result["gemini"] = "ok"
    elif gemini_key:
        result["gemini"] = "warning"
    else:
        result["gemini"] = "no_key"

    # Instagram
    ig_token = env.get("INSTAGRAM_ACCESS_TOKEN", "")
    ig_user = env.get("INSTAGRAM_USER_ID", "")
    if ig_token and ig_user:
        # 간단 핑
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://graph.facebook.com/v18.0/me",
                    params={"fields": "id", "access_token": ig_token}
                )
                if r.status_code == 200:
                    result["instagram"] = "ok"
                else:
                    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    err_code = data.get("error", {}).get("code")
                    if err_code == 190:
                        result["instagram"] = "expired"
                    else:
                        result["instagram"] = "error"
        except Exception:
            result["instagram"] = "error"
    else:
        result["instagram"] = "no_key"

    # Cloudinary
    cloud_name = env.get("CLOUDINARY_CLOUD_NAME", "")
    cloud_key = env.get("CLOUDINARY_API_KEY", "")
    if cloud_name and cloud_key:
        result["cloudinary"] = "ok"
    else:
        result["cloudinary"] = "no_key"

    return result
