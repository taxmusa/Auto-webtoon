"""
템플릿 세트 프리뷰 이미지 생성 스크립트

각 템플릿 세트의 커버를 샘플 데이터로 렌더링하여 PNG로 저장.
한번만 실행하면 되고, 서버 재시작 시 재실행 불필요.
새 템플릿 추가 시에만 다시 실행.

사용법: python generate_previews.py
"""
import asyncio
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.template_builders import build_template_slide
from app.services.theme_palettes import TEMPLATE_SETS

# 프리뷰 저장 경로
PREVIEW_DIR = os.path.join(os.path.dirname(__file__), "app", "static", "previews")

# 샘플 데이터 (프리뷰용)
SAMPLE_TITLE = "2026년 꼭 알아야 할\n절세 포인트 5가지"
SAMPLE_BODY = "세무 · 회계 · 법률\n핵심 정보를 한눈에"


async def generate_all_previews():
    """모든 템플릿 세트의 커버 프리뷰 이미지를 생성"""
    from app.services.render_service import render_html_to_image

    os.makedirs(PREVIEW_DIR, exist_ok=True)

    print(f"프리뷰 저장 경로: {PREVIEW_DIR}")
    print(f"총 {len(TEMPLATE_SETS)}개 세트 프리뷰 생성 시작...\n")

    for set_id, ts in TEMPLATE_SETS.items():
        output_path = os.path.join(PREVIEW_DIR, f"{set_id}.png")

        # 커버 슬라이드 HTML 생성 (index 0 = 커버)
        html = build_template_slide(
            template_set=set_id,
            slide_index=0,
            total_slides=5,
            title=SAMPLE_TITLE,
            body=SAMPLE_BODY,
            width=1080,
            height=1350,
        )

        # Playwright로 렌더링
        await render_html_to_image(
            html_content=html,
            width=1080,
            height=1350,
            output_path=output_path,
            device_scale_factor=0.25,  # 270x338 썸네일 크기
        )

        file_size = os.path.getsize(output_path) / 1024
        print(f"  [{set_id}] {ts['label']} → {file_size:.1f}KB 저장 완료")

    print(f"\n모든 프리뷰 이미지 생성 완료! ({PREVIEW_DIR})")


async def main():
    try:
        await generate_all_previews()
    finally:
        from app.services.render_service import shutdown_browser
        await shutdown_browser()


if __name__ == "__main__":
    asyncio.run(main())
