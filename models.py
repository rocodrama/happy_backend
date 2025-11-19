from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# 1. 유저 테이블
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    nickname = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    diaries = relationship("Diary", back_populates="owner", cascade="all, delete")


# 2. 일기 원본 테이블
class Diary(Base):
    __tablename__ = "diaries"

    diary_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    original_content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="diaries")
    stories = relationship("Story", back_populates="diary", cascade="all, delete")

    cascade="all, delete-orphan", 
    passive_deletes=True


# 3. 각색된 스토리 테이블
class Story(Base):
    __tablename__ = "stories"

    story_id = Column(Integer, primary_key=True, index=True)
    diary_id = Column(Integer, ForeignKey("diaries.diary_id", ondelete="CASCADE"))
    full_story = Column(Text)
    genre = Column(String)
    style = Column(String)
    character_note = Column(Text)
    total_cuts = Column(Integer, default=4) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    diary = relationship("Diary", back_populates="stories")
    cuts = relationship("Cut", back_populates="story", cascade="all, delete-orphan",passive_deletes=True)


# 4. 컷 별 상세 정보 테이블
class Cut(Base):
    __tablename__ = "cuts"

    cut_id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.story_id", ondelete="CASCADE"))
    
    cut_number = Column(Integer, nullable=False) # 1, 2, 3, 4
    cut_content = Column(Text)                   # 컷 별 대사/상황
    image_prompt = Column(Text)                  # 영어 프롬프트
    image_url = Column(Text)                     # 생성된 이미지 주소
    status = Column(String, default="pending")   # 생성 상태
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    story = relationship("Story", back_populates="cuts")