"""
AHA TTS API Server
-------------------
یک سرور ساده که موتور TTS را از طریق HTTP در دسترس پروژه‌های دیگر
(مثل دستیار هوشمند شما) قرار می‌دهد.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .engine import AhaTTSEngine

app = FastAPI(title="AHA TTS Engine", version="0.2.0")

# موتور عمداً این‌جا ساخته نمی‌شود (لود مدل ممکن است طول بکشد)؛
# در اولین درخواست واقعی ساخته می‌شود تا پورت سریع باز شود.
_engine: AhaTTSEngine | None = None


def get_engine() -> AhaTTSEngine:
    global _engine
    if _engine is None:
        _engine = AhaTTSEngine()
    return _engine


class TTSRequest(BaseModel):
    text: str
    lang: str | None = None  # "fa" یا "en"؛ اگر خالی باشد خودکار تشخیص داده می‌شود


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tts")
def tts(req: TTSRequest):
    try:
        audio_bytes = get_engine().synthesize_to_bytes(req.text, lang=req.lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(content=audio_bytes, media_type="audio/wav")
