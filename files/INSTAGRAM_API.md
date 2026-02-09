# INSTAGRAM_API.md - Instagram Graph API 연동

> 이 문서는 Instagram 발행 관련 로직을 정의합니다.

---

## 1. 사전 요구사항

### 1.1 필요한 것

- **Instagram Business 계정** (개인 계정 X)
- **Facebook 페이지** (인스타 계정과 연결)
- **Facebook App** (개발자 계정에서 생성)
- **Access Token** (장기 토큰 권장)

### 1.2 필요 권한

```
instagram_basic
instagram_content_publish
pages_read_engagement
```

---

## 2. 캐러셀 발행 흐름

### 2.1 전체 흐름

```
[이미지 업로드] → [미디어 컨테이너 생성] → [캐러셀 컨테이너 생성] → [발행]
```

### 2.2 단계별 API 호출

**Step 1: 개별 이미지 컨테이너 생성**

```python
async def create_image_container(image_url: str, ig_user_id: str, access_token: str):
    url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
    params = {
        "image_url": image_url,  # 공개 URL 필요 (Cloudinary 등)
        "is_carousel_item": True,
        "access_token": access_token
    }
    response = await httpx.post(url, params=params)
    return response.json()["id"]  # container_id 반환
```

**Step 2: 캐러셀 컨테이너 생성**

```python
async def create_carousel_container(
    container_ids: List[str], 
    caption: str,
    ig_user_id: str, 
    access_token: str
):
    url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(container_ids),
        "caption": caption,
        "access_token": access_token
    }
    response = await httpx.post(url, params=params)
    return response.json()["id"]  # carousel_container_id
```

**Step 3: 발행**

```python
async def publish_carousel(carousel_container_id: str, ig_user_id: str, access_token: str):
    url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish"
    params = {
        "creation_id": carousel_container_id,
        "access_token": access_token
    }
    response = await httpx.post(url, params=params)
    return response.json()["id"]  # 발행된 media_id
```

---

## 3. 제약사항

### 3.1 캐러셀 제한

| 항목 | 제한 |
|------|------|
| 최대 이미지 수 | 10장 |
| 이미지 비율 | 1:1 ~ 1.91:1 (4:5 권장) |
| 이미지 형식 | JPEG, PNG |
| 최소 해상도 | 320px |
| 최대 파일 크기 | 8MB |

### 3.2 캡션 제한

| 항목 | 제한 |
|------|------|
| 최대 길이 | 2,200자 |
| 해시태그 | 최대 30개 |

---

## 4. 예약 발행

Instagram Graph API는 직접 예약을 지원하지 않음.

**대안**:
1. 서버에서 스케줄러로 예약 시간에 발행
2. n8n의 Schedule 노드 활용

```python
# 예약 발행 로직
async def schedule_publish(publish_data: PublishData, scheduled_time: datetime):
    # DB에 예약 정보 저장
    await save_scheduled_post(publish_data, scheduled_time)
    
    # 스케줄러가 해당 시간에 publish 실행
```

---

## 5. 에러 처리

| 에러 코드 | 의미 | 대응 |
|-----------|------|------|
| 190 | Invalid OAuth | 토큰 갱신 필요 |
| 10 | Permission denied | 권한 확인 |
| 36003 | Rate limit | 대기 후 재시도 |
| 2207026 | Invalid image | 이미지 URL 확인 |

---

## 6. 발행 워크플로우 (Python)

```python
async def publish_carousel_workflow(images: List[str], caption: str, settings: PublishSettings):
    """전체 캐러셀 발행 워크플로우"""
    
    # 1. 이미지들을 Cloudinary에 업로드 (공개 URL 필요)
    public_urls = await upload_to_cloudinary(images)
    
    # 2. 각 이미지의 미디어 컨테이너 생성
    container_ids = []
    for url in public_urls:
        container_id = await create_image_container(url, settings.ig_user_id, settings.access_token)
        container_ids.append(container_id)
    
    # 3. 캐러셀 컨테이너 생성
    carousel_id = await create_carousel_container(container_ids, caption, settings.ig_user_id, settings.access_token)
    
    # 4. 발행
    media_id = await publish_carousel(carousel_id, settings.ig_user_id, settings.access_token)
    
    return {"success": True, "media_id": media_id}
```

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2026-02-06 | 1.0.0 | 초기 작성 |
