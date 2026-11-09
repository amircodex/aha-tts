"""
AHA TTS Engine
--------------
موتور تبدیل متن به صدا برای فارسی و انگلیسی.

- کاملاً محلی: تولید صدا روی سیستم خودتان انجام می‌شود (نه از طریق API ابری).
- مبتنی بر مدل‌های متن‌باز MMS (Meta) که از طریق کتابخانه transformers بارگذاری می‌شوند.
- تنها اتصال اینترنت مورد نیاز، دانلود یک‌بارهٔ وزن‌های مدل از HuggingFace Hub است؛
  پس از آن، موتور کاملاً آفلاین کار می‌کند.

نصب پیش‌نیازها:
    pip install torch transformers soundfile uroman

نکته مهم درباره فارسی:
    مدل‌های MMS برای زبان‌هایی که خط غیرلاتین دارند (مثل فارسی) باید قبل از
    توکنایز شدن با کتابخانه uroman «رومن‌نویسی آوایی» بشن. جا انداختن این
    مرحله باعث می‌شه مدل حروف رو اشتباه تشخیص بده: هم تلفظ بد می‌شه، هم گاهی
    حرف/هجای اول از قلم می‌افته. این نسخه این مرحله را به‌درستی انجام می‌دهد.
"""

import re
import io

import numpy as np
import torch
import soundfile as sf
from transformers import VitsModel, AutoTokenizer

try:
    import uroman as ur
    _UROMAN = ur.Uroman()
except ImportError:
    _UROMAN = None

# مدل‌های پیش‌فرض برای هر زبان (قابل تغییر یا افزودن زبان جدید)
MODEL_IDS = {
    "fa": "facebook/mms-tts-fas",  # فارسی
    "en": "facebook/mms-tts-eng",  # انگلیسی
}

# کد زبان ISO-639-3 که uroman برای رومن‌سازی درست به آن نیاز دارد
UROMAN_LANG_CODES = {
    "fa": "fas",
    "en": "eng",
}

# مقدار سکوت (بر حسب ثانیه) که ابتدا و انتهای صدا اضافه می‌شود تا اولین
# هجای گفتار به‌خاطر عدم "گرم شدن" مدل یا کات شدن توسط پخش‌کننده از دست نرود
LEADING_SILENCE_SEC = 0.15
TRAILING_SILENCE_SEC = 0.1


class AhaTTSEngine:
    """موتور اصلی AHA TTS. یک بار ساخته می‌شود و برای چندین درخواست synthesize قابل استفاده مجدد است."""

    def __init__(self, device: str = None, preload=("fa", "en")):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._models = {}
        self._tokenizers = {}
        for lang in preload:
            self._load(lang)

    def _load(self, lang: str):
        if lang not in MODEL_IDS:
            raise ValueError(
                f"زبان '{lang}' پشتیبانی نمی‌شود. زبان‌های مجاز: {list(MODEL_IDS.keys())}"
            )
        if lang not in self._models:
            model_id = MODEL_IDS[lang]
            self._tokenizers[lang] = AutoTokenizer.from_pretrained(model_id)
            model = VitsModel.from_pretrained(model_id)
            model.to(self.device)
            model.eval()
            self._models[lang] = model
        return self._models[lang], self._tokenizers[lang]

    @staticmethod
    def detect_language(text: str) -> str:
        """تشخیص ساده زبان بر اساس وجود حروف فارسی/عربی در متن."""
        if re.search(r"[\u0600-\u06FF]", text):
            return "fa"
        return "en"

    def _prepare_text(self, text: str, lang: str, tokenizer) -> str:
        """در صورت نیاز مدل، متن را با uroman رومن‌نویسی آوایی می‌کند."""
        needs_uroman = getattr(tokenizer, "is_uroman", False)
        if not needs_uroman:
            return text
        if _UROMAN is None:
            raise RuntimeError(
                "این مدل به کتابخانه uroman نیاز دارد اما نصب نشده. "
                "دستور: pip install uroman"
            )
        lcode = UROMAN_LANG_CODES.get(lang)
        return _UROMAN.romanize_string(text, lcode=lcode)

    def synthesize(self, text: str, lang: str = None):
        """تبدیل متن به موج صوتی (numpy array) و نرخ نمونه‌برداری."""
        if not text or not text.strip():
            raise ValueError("متن ورودی خالی است.")

        lang = lang or self.detect_language(text)
        model, tokenizer = self._load(lang)

        prepared_text = self._prepare_text(text, lang, tokenizer)

        inputs = tokenizer(prepared_text, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            output = model(**inputs).waveform

        waveform = output.squeeze().cpu().numpy().astype(np.float32)
        sample_rate = model.config.sampling_rate

        # افزودن سکوت ابتدا/انتها تا ابتدای گفتار به هیچ عنوان قطع نشود
        lead = np.zeros(int(sample_rate * LEADING_SILENCE_SEC), dtype=np.float32)
        tail = np.zeros(int(sample_rate * TRAILING_SILENCE_SEC), dtype=np.float32)
        waveform = np.concatenate([lead, waveform, tail])

        return waveform, sample_rate

    def synthesize_to_file(self, text: str, out_path: str, lang: str = None) -> str:
        """تولید صدا و ذخیره مستقیم در فایل (wav)."""
        waveform, sr = self.synthesize(text, lang=lang)
        sf.write(out_path, waveform, sr)
        return out_path

    def synthesize_to_bytes(self, text: str, lang: str = None, fmt: str = "WAV") -> bytes:
        """تولید صدا و برگرداندن آن به صورت bytes (مناسب برای پاسخ API یا استریم)."""
        waveform, sr = self.synthesize(text, lang=lang)
        buf = io.BytesIO()
        sf.write(buf, waveform, sr, format=fmt)
        buf.seek(0)
        return buf.read()


if __name__ == "__main__":
    # تست سریع محلی
    engine = AhaTTSEngine()
    engine.synthesize_to_file("Hello, this is a test.", "test_en.wav", lang="en")
    engine.synthesize_to_file("سلام، این یک تست است.", "test_fa.wav", lang="fa")
    print("فایل‌های تست ساخته شدند: test_en.wav و test_fa.wav")
