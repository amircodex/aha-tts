"""
AHA TTS API Server
-------------------
یک سرور ساده که موتور TTS را از طریق HTTP در دسترس پروژه‌های دیگر
(مثل دستیار هوشمند شما) قرار می‌دهد.
"""

import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .engine import AhaTTSEngine, memory_info

app = FastAPI(title="AHA TTS Engine", version="0.2.0")

# موتور عمداً این‌جا ساخته نمی‌شود (لود مدل ممکن است طول بکشد)؛
# در اولین درخواست واقعی ساخته می‌شود تا پورت سریع باز شود.
_engine: AhaTTSEngine | None = None


_engine_lock = threading.Lock()


def get_engine() -> AhaTTSEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = AhaTTSEngine()
    return _engine


@app.on_event("startup")
def warm_up():
    """مدل فارسی را در پس‌زمینه لود می‌کند تا اولین درخواست واقعی کند نباشد
    (پورت بلافاصله باز می‌شود و Render تایم‌اوت نمی‌کند)."""
    def _warm():
        try:
            get_engine()
        except Exception as e:  # نباید سرور را از کار بیندازد
            print("warm-up failed:", e)
    threading.Thread(target=_warm, daemon=True).start()


@app.get("/memory")
def memory():
    """مصرف رم فعلی سرور (برای اطمینان از ماندن زیر ۵۱۲ مگابایت)."""
    info = memory_info()
    info["loaded_voices"] = list(_engine._voices.keys()) if _engine else []
    info["limit_mb"] = 512
    return info


class TTSRequest(BaseModel):
    text: str
    lang: str | None = None  # "fa" یا "en"؛ اگر خالی باشد خودکار تشخیص داده می‌شود


@app.get("/health")
def health():
    return {"status": "ok", "ready": _engine is not None}


@app.post("/tts")
def tts(req: TTSRequest):
    try:
        audio_bytes = get_engine().synthesize_to_bytes(req.text, lang=req.lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(content=audio_bytes, media_type="audio/wav")
