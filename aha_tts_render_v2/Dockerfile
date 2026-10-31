FROM python:3.10-slim

WORKDIR /app

# espeak-ng به‌عنوان پشتیبان (بعضی نسخه‌های piper-phonemize خودشون
# باینری لازم رو همراه دارن، ولی اگه نداشته باشن این جلوی خطا رو می‌گیره)
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aha_tts ./aha_tts

EXPOSE 8000

CMD ["sh", "-c", "uvicorn aha_tts.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
