import json
import os
import time
import uuid
from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles 
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt
from dotenv import load_dotenv

import google.generativeai as genai
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

import models, schemas
from database import engine, get_db
from prompts import SYSTEM_PROMPT_TEMPLATE, USER_PROMPT_TEMPLATE, IMAGE_PROMPT_TEMPLATE

from google.cloud import storage

load_dotenv()

# 기존 테이블 삭제
# models.Base.metadata.drop_all(bind=engine)

# 테이블 생성
models.Base.metadata.create_all(bind=engine)

# Google AI 모델

# Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini_model = genai.GenerativeModel(
    model_name="gemini-2.5-pro",
    generation_config={"response_mime_type": "application/json"} 
)

# Imagen   
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
vertexai.init(project=project_id, location=location)
imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006") 

app = FastAPI(
    title="오늘 맑음 API",
    description="Gemini와 Imagen을 이용한 AI 그림 일기장 서비스 API 명세서입니다.",
    version="1.0.0"
)

# 이미지 파일 경로 설정
# os.makedirs("static/images", exist_ok=True)
# app.mount("/static", StaticFiles(directory="static"), name="static")

storage_client = storage.Client()
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

def upload_to_gcs(source_file_name, destination_blob_name):
    """로컬 파일을 GCS에 올리고 공개 URL을 반환합니다."""
    
    # [NEW] 함수 내에서 BUCKET_NAME을 직접 읽거나, 전역 변수를 사용하되 오류 시 처리
    bucket_name = os.getenv("GCS_BUCKET_NAME") 
    
    # 만약 환경 변수가 없으면 오류 발생
    if not bucket_name:
        raise Exception("GCS_BUCKET_NAME 환경 변수가 설정되지 않았거나 로드 실패.")
        
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        
        # 파일 업로드
        blob.upload_from_filename(source_file_name)

        # 공개 URL 반환
        return f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}"
    except Exception as e:
        print(f"GCS Upload Error: {e}")
        # 오류가 나더라도 다음 처리를 위해 예외를 다시 발생시킵니다.
        raise e

# CORS 설정 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # frontend 주소
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 토큰 생성 함수
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# API 

@app.get("/")
def read_root():
    return {"Hello": "World"}

# 회원가입 API
@app.post("/api/users/signup", status_code=status.HTTP_201_CREATED, tags=["Auth"], summary="회원가입")
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")

    hashed_password = pwd_context.hash(user.password)

    new_user = models.User(
        email=user.email,
        password=hashed_password, 
        nickname=user.nickname
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "회원가입 성공", "user_id": new_user.user_id}

# 로그인 API
@app.post("/api/auth/login", tags=["Auth"], summary="로그인 및 토큰 발급")
def login(user_request: schemas.UserLogin, db: Session = Depends(get_db)):
    
    user = db.query(models.User).filter(models.User.email == user_request.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 잘못되었습니다.")

    if not pwd_context.verify(user_request.password, user.password):
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 잘못되었습니다.")

    access_token = create_access_token(data={"sub": user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "nickname": user.nickname
    }
    
# 일기 생성 API
@app.post("/api/diaries", tags=["Diary"], summary="일기 생성 (LLM + Imagen)")
def create_diary(request: schemas.DiaryCreateRequest, db: Session = Depends(get_db)):
    print("1. 일기 생성 요청 받음 (Google Models)")

    # 원본 저장
    new_diary = models.Diary(user_id=request.user_id, original_content=request.original_content)
    db.add(new_diary)
    db.commit()
    db.refresh(new_diary)
    print(f"2. 원본 저장 완료: {new_diary.diary_id}")

    # Gemini 프롬프트 
    formatted_user_prompt = USER_PROMPT_TEMPLATE.format(
        original_content=request.original_content,
        genre=request.genre,
        style=request.style,
        character=request.character_note,
        cuts=request.cuts_count
    )
    
    llm_result = {}
    try:
        # Gemini 호출
        response = gemini_model.generate_content(
            f"{SYSTEM_PROMPT_TEMPLATE.format(cuts=request.cuts_count)}\n{formatted_user_prompt}"
        )
        llm_result = json.loads(response.text)
        print("3. Gemini 각색 완료")
    except Exception as e:
        print(f"Gemini 에러: {e}")
        raise HTTPException(status_code=500, detail=f"AI 스토리 생성 실패: {str(e)}")

    # 스토리 저장
    new_story = models.Story(
        diary_id=new_diary.diary_id,
        full_story=llm_result.get("full_story", ""),
        genre=request.genre,
        style=request.style,
        character_note=request.character_note,
        total_cuts=request.cuts_count 
    )
    db.add(new_story)
    db.commit()
    db.refresh(new_story)

    # Imagen으로 이미지 생성 및 저장
    cuts_data = llm_result.get("cuts", [])
    
    for i, cut in enumerate(cuts_data):
        cut_no = i + 1
        scene_desc = cut.get("scene_description", "")
        
        # Imagen 프롬프트
        final_image_prompt = IMAGE_PROMPT_TEMPLATE.format(
            style=request.style,
            character=request.character_note,
            action_description=scene_desc,
            background_description=cut.get("image_prompt", "") # Gemini가 준 프롬프트
        )

        image_url = ""
        try:
            print(f"   - {cut_no}번 컷 생성 중 (Imagen)...")
            
            # Imagen 호출 (이미지 데이터 반환)
            response = imagen_model.generate_images(
                prompt=final_image_prompt,
                number_of_images=1,
                aspect_ratio="1:1", 
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )

            
            if not response or not response.images:
                raise ValueError("Imagen이 이미지를 반환하지 않았습니다. (안전 필터 차단)")
            
            # [중요] 이미지를 서버 폴더에 저장
            filename = f"{new_story.story_id}_{cut_no}_{uuid.uuid4().hex[:8]}.png"
            
            temp_path = f"temp_{filename}"
            
            # [수정] response.images[0]으로 접근해야 함
            response.images[0].save(location=temp_path, include_generation_parameters=False)
            image_url = upload_to_gcs(temp_path, filename)
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
            print(f"   -> GCS 업로드 완료: {image_url}")

        except Exception as e:
            print(f"   - Imagen 실패 ({cut_no}컷): {e}")
            image_url = "https://via.placeholder.com/1024?text=Generation+Failed"

        # DB 저장
        new_cut = models.Cut(
            story_id=new_story.story_id,
            cut_number=cut_no,
            cut_content=cut.get("dialogue", ""),
            image_prompt=final_image_prompt,
            image_url=image_url,
            status="completed" if "http" in image_url else "failed"
        )
        db.add(new_cut)
    
    db.commit()
    print("5. 생성 완료")

    return {"message": "일기 생성 완료", "diary_id": new_diary.diary_id}

# 일기 목록 조회
@app.get("/api/diaries", tags=["Diary"], summary="내 일기 목록 조회")
def get_diary_list(user_id: int, db: Session = Depends(get_db)):
    # Story와 Diary를 조인해서 가져옴
    results = db.query(models.Diary, models.Story).\
        join(models.Story, models.Story.diary_id == models.Diary.diary_id).\
        filter(models.Diary.user_id == user_id).\
        order_by(models.Diary.created_at.desc()).all()
    
    response = []
    for diary, story in results:
        response.append({
            "diary_id": diary.diary_id,
            "date": diary.created_at.strftime("%Y-%m-%d"),
            "original_content": diary.original_content,
            "full_story": story.full_story
        })
    return response

# 일기 상세 조회
@app.get("/api/diaries/{diary_id}", tags=["Diary"], summary="일기 상세 조회")
def get_diary_detail(diary_id: int, db: Session = Depends(get_db)):
    diary = db.query(models.Diary).filter(models.Diary.diary_id == diary_id).first()
    if not diary:
        raise HTTPException(status_code=404, detail="일기를 찾을 수 없습니다.")
        
    story = db.query(models.Story).filter(models.Story.diary_id == diary_id).first()
    cuts = db.query(models.Cut).filter(models.Cut.story_id == story.story_id).order_by(models.Cut.cut_number).all()
    
    return {
        "diary_id": diary.diary_id,
        "date": diary.created_at.strftime("%Y-%m-%d"),
        "original_content": diary.original_content,
        "full_story": story.full_story,
        "settings": {
            "genre": story.genre,
            "style": story.style,
            "character": story.character_note,
            "cuts": story.total_cuts
        },
        "cuts": [
            {
                "cut_id": cut.cut_id,
                "cut_number": cut.cut_number,
                "image_url": cut.image_url,
                "text": cut.cut_content
            } for cut in cuts
        ]
    }
    
# 6. 일기 수정 API (PUT)
@app.put("/api/diaries/{diary_id}", tags=["Diary"], summary="일기 내용 수정 (텍스트만)")
def update_diary(diary_id: int, request: schemas.DiaryUpdateRequest, db: Session = Depends(get_db)):
    # 1. 일기 찾기
    diary = db.query(models.Diary).filter(models.Diary.diary_id == diary_id).first()
    if not diary:
        raise HTTPException(status_code=404, detail="일기를 찾을 수 없습니다.")
    
    # 2. 스토리 찾기 (Story 테이블 업데이트)
    story = db.query(models.Story).filter(models.Story.diary_id == diary_id).first()

    # 3. 내용 업데이트 (원문, 전체 스토리만 업데이트)
    # 3-1. 원본 업데이트
    diary.original_content = request.original_content
    # 3-2. 각색 스토리 업데이트 (프론트에서 수정 불가하지만, API는 대비)
    story.full_story = request.full_story 

    # 4. 컷 별 대사 업데이트 (프론트에서 수정은 막았지만, 혹시 모를 대사 수정을 대비)
    for cut_data in request.cuts:
        cut = db.query(models.Cut).filter(models.Cut.cut_id == cut_data.cut_id).first()
        if cut:
            cut.cut_content = cut_data.text
    
    db.commit()
    return {"message": "텍스트 수정 성공"}

# 일기 전체 재생성 API
@app.post("/api/diaries/{diary_id}/regenerate", tags=["Diary"], summary="일기 전체 재생성 (AI 재실행)")
def regenerate_full_diary(diary_id: int, request: schemas.FullRegenerateRequest, db: Session = Depends(get_db)):
    print(f"1. 전체 재생성 요청 받음 (Diary ID: {diary_id})")

    # 기존 일기 및 스토리 정보 로드
    diary = db.query(models.Diary).filter(models.Diary.diary_id == diary_id).first()
    story = db.query(models.Story).filter(models.Story.diary_id == diary_id).first()
    if not diary or not story:
        raise HTTPException(status_code=404, detail="일기를 찾을 수 없습니다.")

    # 1. 원본 일기 업데이트
    diary.original_content = request.original_content
    db.commit()
    db.refresh(diary)
    print("2. 원본 업데이트 완료")


    # 2. Gemini에게 각색 요청 (기존 설정값 재활용)
    formatted_user_prompt = USER_PROMPT_TEMPLATE.format(
        original_content=request.original_content,
        genre=story.genre,
        style=story.style,
        character=story.character_note,
        cuts=story.total_cuts
    )
    
    try:
        # Gemini 호출
        response = gemini_model.generate_content(
            f"{SYSTEM_PROMPT_TEMPLATE.format(cuts=story.total_cuts)}\n{formatted_user_prompt}"
        )
        llm_result = json.loads(response.text)
        print("3. Gemini 각색 완료")
    except Exception as e:
        print(f"Gemini 에러: {e}")
        raise HTTPException(status_code=500, detail="AI 스토리 생성 실패")

    # 3. 스토리 및 컷 삭제 (재생성 전 기존 데이터 정리)
    db.query(models.Cut).filter(models.Cut.story_id == story.story_id).delete()
    # Story 테이블 필드 업데이트 (full_story만)
    story.full_story = llm_result.get("full_story", "")
    db.commit() 
    print("4. 기존 컷 정보 삭제 및 스토리 업데이트 완료")

    # 4. Imagen으로 이미지 생성 및 Cuts 테이블에 저장 [기존 코드에서 누락된 부분]
    cuts_data = llm_result.get("cuts", [])
    
    for i, cut in enumerate(cuts_data):
        cut_no = i + 1
        scene_desc = cut.get("dialogue", "") # 컷에 들어갈 대사
        image_prompt_text = cut.get("image_prompt", "") # Imagen용 영문 프롬프트

        # 이미지 생성을 위한 최종 프롬프트 조립
        final_image_prompt = IMAGE_PROMPT_TEMPLATE.format(
            style=story.style,
            character=story.character_note,
            action_description=scene_desc,
            background_description=image_prompt_text
        )

        image_url = ""
        try:
            print(f"   - {cut_no}번 컷 이미지 재생성 중...")
            
            # [수정] 응답 객체 받기
            img_response = imagen_model.generate_images(
                prompt=final_image_prompt,
                number_of_images=1,
                aspect_ratio="1:1",
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )

            # [수정] .images 속성 확인
            if not img_response or not img_response.images:
                raise ValueError("Imagen이 이미지를 반환하지 않았습니다. (Safety Filter 차단 가능성)")
            
            # 파일 저장 및 URL 생성
            filename = f"{story.story_id}_{cut_no}_{uuid.uuid4().hex[:8]}_regen.png"
            temp_path = f"temp_{filename}"
            
            # [수정] .images[0] 사용
            img_response.images[0].save(location=temp_path, include_generation_parameters=False)
            
            image_url = upload_to_gcs(temp_path, filename)
            
            # 4. 임시 파일 삭제 (청소)
            if os.path.exists(temp_path):
                os.remove(temp_path)

            print(f"   -> GCS 업로드 완료: {image_url}")
            
        except Exception as e:
            print(f"   - 이미지 생성 실패 ({cut_no}컷): {e}")
            image_url = "https://via.placeholder.com/1024?text=Generation+Failed" 

        # DB에 컷 정보 저장
        new_cut = models.Cut(
            story_id=story.story_id,
            cut_number=cut_no,
            cut_content=cut.get("dialogue", ""),
            image_prompt=final_image_prompt,
            image_url=image_url,
            status="completed" if "http" in image_url else "failed"
        )
        db.add(new_cut)
    
    db.commit()
    print("6. 모든 데이터 재생성 완료")

    return {"message": "전체 재생성 성공", "diary_id": diary_id}

# 7. 컷 이미지 재생성 API (POST)
@app.post("/api/cuts/{cut_id}/regenerate", tags=["Cut"], summary="특정 컷 이미지 재생성")
def regenerate_cut(cut_id: int, request: schemas.RegenerateRequest, db: Session = Depends(get_db)):
    
    cut = db.query(models.Cut).filter(models.Cut.cut_id == cut_id).first()
    story = db.query(models.Story).filter(models.Story.story_id == cut.story_id).first()
    if not cut or not story:
        raise HTTPException(status_code=404, detail="컷/스토리를 찾을 수 없습니다.")

    # 1. 프롬프트 결정 (DB에 저장된 기존 image_prompt를 재활용)
    target_prompt = request.prompt_override if request.prompt_override else cut.image_prompt


    new_image_url = ""
    try:
        print(f"   - {cut.cut_number}번 컷 이미지 재생성 중...")
        
        # --- [NEW/실제 로직] 이미지 생성 및 저장 ---
        
        # Imagen 호출
        response = imagen_model.generate_images(
            prompt=target_prompt,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_some",
            person_generation="allow_adult"
        )
        
        # [수정] .images 리스트 확인
        if not response or not response.images:
            raise ValueError("Imagen이 이미지를 반환하지 않았습니다. (안전 필터 차단)")

        # 파일명 생성 및 저장 (고유 ID 사용)
        filename = f"{story.story_id}_{cut.cut_number}_{uuid.uuid4().hex[:8]}_regen.png"
        
        temp_path = f"temp_{filename}"
        
        # [수정] response.images[0] 사용
        response.images[0].save(location=temp_path, include_generation_parameters=False)
        new_image_url = upload_to_gcs(temp_path, filename)
        
        if os.path.exists(temp_path):
                os.remove(temp_path)

        print(f"   -> GCS 업로드 완료: {new_image_url}")
        
    except Exception as e:
        print(f"   - 재생성 실패: {e}")
        # 실패 시에도 프론트엔드가 깨지지 않게 임시 URL 또는 에러 URL을 보냅니다.
        new_image_url = "https://via.placeholder.com/1024?text=Regeneration+Failed"
        # 에러 발생 시 500 에러를 반환하는 대신 로그를 남기고 저장하도록 수정 가능
        # raise HTTPException(status_code=500, detail="이미지 재생성 실패") # 500을 띄우는 대신, 200과 함께 임시 URL 반환 가능

    # 4. DB 업데이트
    cut.image_url = new_image_url
    cut.image_prompt = target_prompt
    db.commit()

    return {"new_image_url": new_image_url}

@app.delete("/api/diaries/{diary_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Diary"], summary="일기 삭제")
def delete_diary(diary_id: int, db: Session = Depends(get_db)):
    
    # 1. 삭제할 일기 객체 조회
    diary = db.query(models.Diary).filter(models.Diary.diary_id == diary_id).first()
    
    if not diary:
        raise HTTPException(status_code=404, detail="삭제할 일기를 찾을 수 없습니다.")

    # 2. 삭제 실행 (수정된 부분)
    # db.delete()를 쓰면 SQLAlchemy가 모델의 cascade 설정을 보고 
    # 연관된 Story, Cut을 알아서 먼저 지워줍니다. (DB 설정이 없어도 동작)
    db.delete(diary) 
    db.commit()

    # 3. 반환
    return Response(status_code=status.HTTP_204_NO_CONTENT)
