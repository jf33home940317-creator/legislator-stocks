# 基底映像檔：已經裝好 Python 3.12 的精簡 Linux
FROM python:3.12-slim

# 環境變數：不產生 .pyc 快取、輸出不緩衝（log 即時顯示）
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# 先只複製套件清單再安裝 —— 這樣改程式碼時不用每次重裝套件（Docker 快取）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再複製程式碼
COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

EXPOSE 8000
# 容器啟動時：先把資料庫升級到最新結構，再啟動 API
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.api.main:app --host 0.0.0.0 --port 8000"]
