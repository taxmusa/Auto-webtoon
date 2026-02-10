import os
import json

styles_dir = "app_data/styles"

# Korean descriptions mapping
descriptions = {
    # Character Styles
    "char_webtoon": "깔끔하고 선명한 라인과 생동감 넘치는 색감의 표준 웹툰 스타일입니다.",
    "char_ghibli": "지브리 스튜디오 풍의 감성적이고 부드러운 색채와 동화 같은 분위기입니다.",
    "char_romance": "로맨스 판타지 웹툰 특유의 화려하고 섬세한 이목구비와 반짝이는 효과가 특징입니다.",
    "char_shonen": "소년 만화 스타일로, 역동적인 선과 강렬한 명암 대비가 돋보입니다.",
    "char_chibi": "귀엽고 단순화된 SD(Super Deformed) 캐릭터 스타일입니다.",
    "char_flat_vector": "깔끔한 벡터 그래픽 스타일로, 단순한 면과 색상 중심의 디자인입니다.",
    "char_retro_anime": "90년대 셀 애니메이션 감성의 빈티지한 색감과 노이즈 질감입니다.",
    "char_meme_doodle": "가볍고 웃긴 병맛/낙서 스타일로, 개그 컷에 적합합니다.",
    "char_bw_pen": "흑백 펜화 스타일로, 출판 만화나 누아르 분위기를 연출합니다.",
    "char_crayon": "크레파스나 색연필로 그린 듯한 따뜻하고 아동 친화적인 질감입니다.",
    "char_pixel_art": "도트 그래픽 스타일로, 레트로 게임 같은 분위기를 줍니다.",
    
    # Background Styles
    "bg_anime": "애니메이션 배경처럼 청량하고 디테일한 하늘과 풍경 묘사입니다.",
    "bg_realistic": "실사 영화처럼 사실적인 라이팅과 질감을 가진 고품질 배경입니다.",
    "bg_simple": "인물에 집중할 수 있도록 단순화된 배경이나 단색 패턴입니다."
}

def update_meta_files():
    for type_dir in ["character", "background"]:
        base_path = os.path.join(styles_dir, type_dir)
        if not os.path.exists(base_path):
            continue
            
        for style_id in os.listdir(base_path):
            style_path = os.path.join(base_path, style_id)
            meta_path = os.path.join(style_path, "meta.json")
            
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Update fields
                    if style_id in descriptions:
                        data["description"] = descriptions[style_id]
                        # Ensure name matches the convention if needed, or keep valid
                    else:
                         data["description"] = data.get("name", "스타일 설명")

                    # Add preview image path (placeholder for now)
                    # We point to a file that SHOULD exist in that folder
                    data["preview_image"] = f"/app_data/styles/{type_dir}/{style_id}/preview.png"
                    
                    with open(meta_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    
                    print(f"Updated {style_id}")
                    
                except Exception as e:
                    print(f"Failed to update {style_id}: {e}")

if __name__ == "__main__":
    update_meta_files()
