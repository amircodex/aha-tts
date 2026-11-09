---
title: AHA TTS
emoji: 🗣️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
---

# AHA TTS Engine

موتور تبدیل متن به صدا برای فارسی و انگلیسی — میزبانی‌شده روی Hugging Face Spaces (رایگان).

## استفاده

```bash
curl -X POST https://<YOUR-SPACE-URL>/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "سلام دنیا"}' \
  --output out.wav
```

بررسی سلامت سرویس:
```
GET /health
```
