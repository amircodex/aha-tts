FROM python:3.10-slim

WORKDIR /app

# تنظیمات کاهش مصرف حافظه
ENV MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    PYTHONUNBUFFERED=1

# espeak-ng به‌عنوان پشتیبان (بعضی نسخه‌های piper-phonemize خودشون
# باینری لازم رو همراه دارن، ولی اگه نداشته باشن این جلوی خطا رو می‌گیره)
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aha_tts ./aha_tts

# مدل‌های صوتی را همین‌جا (موقع build) دانلود می‌کنیم تا شروع سرور سریع باشد
RUN python -c "from aha_tts.engine import download_all_models; download_all_models()"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn aha_tts.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
