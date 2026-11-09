# AHA TTS (نسخه سبک Piper) — برای Render

این نسخه به‌جای torch/transformers از **Piper** استفاده می‌کند: یک موتور TTS
بسیار سبک که برای سخت‌افزار کم‌منبع طراحی شده و باید به‌راحتی در ۵۱۲ مگابایت
رم پلن رایگان Render جا بشه.

## جایگزینی کد قبلی
همون‌جوری که قبلاً گفتم:
1. توی ریپوی گیت‌هاب `aha-tts`، فایل‌های زیر رو **کامل جایگزین کن**:
   - `Dockerfile`
   - `requirements.txt`
   - `aha_tts/__init__.py`
   - `aha_tts/engine.py`
   - `aha_tts/server.py`
2. برگرد به Render، منتظر بمون دیپلوی خودکار شروع بشه (یا از Manual Deploy)
3. بعد از سبز شدن، دوباره تست کن:

```bash
curl -X POST https://aha-tts.onrender.com/tts \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"سلام دنیا\"}" \
  --output test.wav
```

اولین درخواست کندتره چون مدل (~۶۰-۷۰ مگابایت) باید دانلود بشه؛ درخواست‌های بعدی سریع‌ان.
