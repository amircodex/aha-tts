FROM python:3.10-slim

WORKDIR /app

# نصب وابستگی‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کد موتور
COPY aha_tts ./aha_tts

# پوشه کش مدل‌ها قابل نوشتن باشد (Hugging Face Spaces با کاربر غیر-روت اجرا می‌کند)
ENV HF_HOME=/app/.cache
RUN mkdir -p /app/.cache && chmod -R 777 /app/.cache

# پورتی که Hugging Face Spaces برای اپ‌های Docker انتظار دارد
EXPOSE 7860

CMD ["uvicorn", "aha_tts.server:app", "--host", "0.0.0.0", "--port", "7860"]
