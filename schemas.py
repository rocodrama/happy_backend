from pydantic import BaseModel
from typing import List, Optional

# 사용자

# 회원가입 요청 데이터
class UserCreate(BaseModel):
    email: str
    password: str
    nickname: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "test@example.com",
                "password": "strongpassword123",
                "nickname": "지브리덕후"
            }
        }

# 로그인 요청 데이터
class UserLogin(BaseModel):
    email: str
    password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "test@example.com",
                "password": "strongpassword123"
            }
        }

# 사용자 정보 반환용 (비밀번호 제외)
class UserResponse(BaseModel):
    user_id: int
    email: str
    nickname: str

    class Config:
        from_attributes = True  

# 일기 생성

# 일기 생성 요청 데이터 (프론트엔드 -> 백엔드)
class DiaryCreateRequest(BaseModel):
    user_id: int
    original_content: str
    genre: str
    style: str
    character_note: str
    cuts_count: int = 4
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "original_content": "오늘 길을 가다가 우연히 보물지도를 주웠다.",
                "genre": "모험/판타지",
                "style": "지브리",
                "character_note": "밀짚모자를 쓴 소년",
                "cuts_count": 4
            }
        }


# 일기 수정 

# 컷 별 수정 데이터 (대사 수정용)
class CutUpdate(BaseModel):
    cut_id: int
    text: str

# 일기 전체 수정 요청 데이터
class DiaryUpdateRequest(BaseModel):
    original_content: str
    full_story: str
    cuts: List[CutUpdate]  
    
    class Config:
        json_schema_extra = {
            "example": {
                "original_content": "수정된 일기 원문입니다.",
                "full_story": "수정된 AI 각색 스토리입니다.",
                "cuts": [
                    {"cut_id": 1, "text": "수정된 1번 컷 대사"},
                    {"cut_id": 2, "text": "수정된 2번 컷 대사"}
                ]
            }
        }
    
# 이미지 재생성

# 전체 재생성 요청 데이터 (원문만 수정 후 전체 AI 파이프라인 재실행용)
class FullRegenerateRequest(BaseModel):
    original_content: str 
    
    class Config:
        json_schema_extra = {
            "example": {
                "original_content": "내용을 완전히 바꿔서 다시 쓰고 싶어. 주인공이 사실은 외계인이었다는 설정으로 바꿔줘."
            }
        }


# 컷 이미지 재생성 요청 데이터
class RegenerateRequest(BaseModel):
    prompt_override: Optional[str] = ""
    
    class Config:
        json_schema_extra = {
            "example": {
                "prompt_override": "A cat flying in the sky, Ghibli style, high quality (비워두면 기존 프롬프트 재사용)"
            }
        }