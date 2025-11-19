# LLM에게 역할을 부여하는 시스템 프롬프트
SYSTEM_PROMPT_TEMPLATE = """
당신은 전문 웹툰 스토리 작가이자 AI 프롬프트 엔지니어입니다.
당신의 모든 출력과 생성된 프롬프트는 **폭력, 선정성, 증오, 불법적인 활동, 자해, 노골적인 콘텐츠를 포함해서는 안 됩니다.**
사용자의 일기를 바탕으로 {cuts}컷 만화의 스크립트와 이미지 생성 프롬프트를 작성해야 합니다.
반드시 아래의 JSON 형식을 정확히 지켜서 답변하세요.
"""

# 실제 작업을 요청하는 유저 프롬프트 (JSON 구조 명시 추가)
USER_PROMPT_TEMPLATE = """
[입력 정보]
- 일기 원문: {original_content}
- 장르: {genre}
- 작화 스타일: {style}
- 캐릭터 특징: {character}

[요청 사항]
1. 위 일기 내용을 {genre} 장르로 각색해서 '전체 줄거리(full_story)'를 작성하세요.
2. **[안전 규정 준수 필수]**: 이미지 모델의 안전 정책에 따라, 생성될 만화 컷에는 나체, 성적인 내용, 유혈이 낭자한 폭력, 혐오스러운 콘텐츠, 불법 활동, 자해 장면이 포함되어서는 안 됩니다.
3. {cuts}개의 장면(Cut)으로 나누어 각 장면의 '대사/지문(dialogue)', '상황 묘사(scene_description)', '이미지 생성용 프롬프트(image_prompt)'를 작성하세요.
4. **이미지 프롬프트(image_prompt)는 반드시 '영어(English)'로 작성해야 하며**, 구체적인 시각적 묘사(조명, 구도, 스타일 등)를 포함해야 합니다.

[필수 출력 포맷 (JSON)]
응답은 오직 아래 JSON 형식으로만 작성하세요. 다른 말은 하지 마세요.

{{
  "full_story": "각색된 전체 줄거리 내용...",
  "cuts": [
    {{
      "cut_number": 1,
      "dialogue": "컷에 들어갈 대사나 지문 (한글)",
      "scene_description": "상황 묘사 (한글)",
      "image_prompt": "Detailed description of the scene, {style} style, {character}, action details... (English)"
    }},
    {{
      "cut_number": 2,
      ...
    }}
  ]
}}
"""

# 이미지 생성(Imagen)용 프롬프트 템플릿
IMAGE_PROMPT_TEMPLATE = """
{background_description}, 
(masterpiece), best quality, high resolution, 
{style} style, {character}, {action_description}, 
cinematic lighting, detailed texture,
"""