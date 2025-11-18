# Python 3.10 기반 이미지 사용
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 파일 복사 (의존성 설치가 빠름)
COPY requirements.txt .

# requirements.txt 파일에 설치된 모든 Python 라이브러리를 추가하세요.
# (예: fastapi, uvicorn, sqlalchemy, psycopg2-binary, passlib[bcrypt], openai, google-cloud-aiplatform 등)
RUN pip install --no-cache-dir -r requirements.txt

COPY service_account.json /app/service_account.json

# 나머지 코드 복사
COPY . .

# .env 파일은 환경변수로 주입되므로 컨테이너에 포함되지 않습니다 (보안).

# 서버 포트 설정 (Cloud Run은 PORT 환경변수를 사용)
ENV PORT 8080

# 서버 실행 명령어
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]