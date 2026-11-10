"""
AHA TTS Engine — نسخه سبک (مبتنی بر Piper)
--------------------------------------------
تولید صدا کاملاً محلی و آفلاین، بدون وابستگی به هیچ API ابری.

ویژگی‌ها:
- فارسی با صدای زن (Mana) و انگلیسی با صدای Lessac
- متن‌های ترکیبی فارسی/انگلیسی: هر بخش با صدای مناسب خودش خوانده می‌شود
- پاک‌سازی نمادها (پرانتز و ...)، تبدیل عدد به حروف، اصلاح املای عربی
- خروجی همیشه WAV با فرمت ۱۶kHz / مونو / ۱۶-بیت
- مصرف رم کم: در هر لحظه فقط «یک» مدل صوتی در حافظه است (فارسی یا انگلیسی)؛
  هنگام تعویض، مدل قبلی آزاد می‌شود. برای متن ترکیبی، قطعه‌های هم‌زبان پشت‌سرهم
  تولید می‌شوند تا تعداد تعویض‌ها کم بماند.
"""

import audioop
import gc
import io
import threading
import wave
from pathlib import Path

import requests
from piper import PiperVoice

from .text_processing import PERSIAN_LETTER_RE, prepare_segments, split_long_text

VOICE_SOURCES = {
    "fa": {
        "onnx_url": "https://huggingface.co/MahtaFetrat/Mana-Persian-Piper/resolve/main/fa_IR-mana-medium.onnx",
        "json_url": "https://huggingface.co/MahtaFetrat/Mana-Persian-Piper/resolve/main/fa_IR-mana-medium.onnx.json",
        "filename": "fa_IR-mana-medium",
    },
    "en": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "filename": "en_US-lessac-medium",
    },
}

MODELS_DIR = Path(__file__).parent / "models"

# فرمت خروجی نهایی (مطابق انتظار Worker)
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
TARGET_SAMPWIDTH = 2  # 16-bit

# مکث کوتاه بین بخش‌های فارسی و انگلیسی (ثانیه)
SEGMENT_PAUSE_SEC = 0.12

# تنظیمات صدا (سرعت کمی آرام‌تر برای فارسی => واضح‌تر)
VOICE_TUNING = {
    "fa": {"length_scale": 1.05, "noise_scale": 0.6, "noise_w_scale": 0.8},
    "en": {"length_scale": 1.0, "noise_scale": 0.667, "noise_w_scale": 0.8},
}


# حداکثر طول هر تکه‌ی متن در یک بار تولید صدا (برای محدود ماندن رم)
MAX_CHUNK_CHARS = 300


def memory_info():
    """مصرف رم فعلی و بیشینه‌ی آن (مگابایت). فقط روی لینوکس کار می‌کند."""
    info = {}
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    info["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
                elif line.startswith("VmHWM:"):
                    info["peak_mb"] = round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return info


def _load_piper_voice_lean(onnx_path: str) -> PiperVoice:
    """
    لود مدل با تنظیمات کم‌مصرف onnxruntime (بدون memory arena، تک‌ریسمانی).
    اگر چیزی در این تنظیمات خطا بدهد، به لود معمولی برمی‌گردد.
    """
    try:
        import onnxruntime as ort
        original = ort.SessionOptions

        def lean_options():
            so = original()
            so.enable_cpu_mem_arena = False
            so.enable_mem_pattern = False
            so.intra_op_num_threads = 1
            so.inter_op_num_threads = 1
            return so

        ort.SessionOptions = lean_options
        try:
            return PiperVoice.load(onnx_path)
        finally:
            ort.SessionOptions = original
    except Exception:
        return PiperVoice.load(onnx_path)


class AhaTTSEngine:
    """موتور اصلی AHA TTS. یک بار ساخته می‌شود و برای چندین درخواست قابل استفاده مجدد است."""

    def __init__(self, preload=("fa",)):
        self._voices = {}
        self._lock = threading.RLock()  # درخواست‌ها پشت‌سرهم پردازش شوند (رم محدود)
        MODELS_DIR.mkdir(exist_ok=True)
        for lang in preload:
            self._load(lang)

    # ------------------------------------------------------------ مدل‌ها

    @staticmethod
    def _download(url: str, dest: Path):
        tmp = dest.with_suffix(dest.suffix + ".part")
        resp = requests.get(url, stream=True, timeout=180)
        resp.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.replace(dest)

    def _ensure_model_files(self, lang: str) -> Path:
        source = VOICE_SOURCES[lang]
        name = source["filename"]
        onnx_path = MODELS_DIR / f"{name}.onnx"
        json_path = MODELS_DIR / f"{name}.onnx.json"
        if not onnx_path.exists():
            self._download(source["onnx_url"], onnx_path)
        if not json_path.exists():
            self._download(source["json_url"], json_path)
        return onnx_path

    def _load(self, lang: str) -> PiperVoice:
        if lang not in VOICE_SOURCES:
            raise ValueError(
                f"زبان '{lang}' پشتیبانی نمی‌شود. زبان‌های مجاز: {list(VOICE_SOURCES.keys())}"
            )
        if lang not in self._voices:
            # ابتدا مدل قبلی را از رم آزاد می‌کنیم، بعد مدل جدید را لود می‌کنیم
            # (تا هیچ‌وقت دو مدل هم‌زمان در حافظه نباشند)
            self._voices.clear()
            gc.collect()
            onnx_path = self._ensure_model_files(lang)
            self._voices[lang] = _load_piper_voice_lean(str(onnx_path))
        return self._voices[lang]

    @staticmethod
    def detect_language(text: str) -> str:
        """تشخیص ساده زبان: اگر حرف فارسی/عربی داشته باشد fa وگرنه en."""
        return "fa" if PERSIAN_LETTER_RE.search(text) else "en"

    # --------------------------------------------------------- تولید صدا

    @staticmethod
    def _to_target_pcm(wav_bytes: bytes) -> bytes:
        """هر WAV را به PCM خام ۱۶kHz / مونو / ۱۶-بیت تبدیل می‌کند."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        if not frames:
            return b""
        if n_channels == 2 and TARGET_CHANNELS == 1:
            frames = audioop.tomono(frames, sampwidth, 0.5, 0.5)
            n_channels = 1
        if sampwidth != TARGET_SAMPWIDTH:
            frames = audioop.lin2lin(frames, sampwidth, TARGET_SAMPWIDTH)
            sampwidth = TARGET_SAMPWIDTH
        if framerate != TARGET_SAMPLE_RATE:
            frames, _ = audioop.ratecv(
                frames, sampwidth, n_channels, framerate, TARGET_SAMPLE_RATE, None
            )
        return frames

    @staticmethod
    def _pcm_to_wav(pcm: bytes) -> bytes:
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(TARGET_CHANNELS)
            wf.setsampwidth(TARGET_SAMPWIDTH)
            wf.setframerate(TARGET_SAMPLE_RATE)
            wf.writeframes(pcm)
        return out.getvalue()

    @staticmethod
    def _synthesis_config(lang: str):
        """تنظیمات صدا (در صورت پشتیبانی نسخه نصب‌شده Piper)."""
        try:
            from piper import SynthesisConfig
            return SynthesisConfig(**VOICE_TUNING[lang])
        except Exception:
            return None

    def _synthesize_segment_pcm(self, text: str, lang: str) -> bytes:
        """متن یک قطعه را (در تکه‌های کوتاه) تولید و به هم می‌چسباند."""
        parts = [self._synthesize_chunk_pcm(c, lang)
                 for c in split_long_text(text, MAX_CHUNK_CHARS)]
        return b"".join(parts)

    def _synthesize_chunk_pcm(self, text: str, lang: str) -> bytes:
        voice = self._load(lang)
        cfg = self._synthesis_config(lang)

        def run(use_cfg):
            buf = io.BytesIO()
            try:
                with wave.open(buf, "wb") as wav_file:
                    if use_cfg is not None:
                        voice.synthesize_wav(text, wav_file, syn_config=use_cfg)
                    else:
                        voice.synthesize_wav(text, wav_file)
            except wave.Error:
                return b""  # متن چیزی برای خواندن نداشت
            return buf.getvalue()

        try:
            wav_bytes = run(cfg)
        except TypeError:
            wav_bytes = run(None)  # نسخه‌ای از Piper که syn_config ندارد
        return self._to_target_pcm(wav_bytes) if wav_bytes else b""

    def synthesize_to_bytes(self, text: str, lang: str = None) -> bytes:
        """تولید صدا و برگرداندن WAV (۱۶kHz/مونو/۱۶-بیت) به‌صورت bytes."""
        if not text or not text.strip():
            raise ValueError("متن ورودی خالی است.")

        segments = prepare_segments(text, lang)
        if not segments:
            raise ValueError("متن قابل خواندنی برای تبدیل به صدا پیدا نشد.")

        with self._lock:
            # زبان‌ها به ترتیب: اول زبانی که همین الان در رم است (بدون لود مجدد)
            langs = list(dict.fromkeys(l for l, _ in segments))
            langs.sort(key=lambda l: l not in self._voices)

            pcm_by_index = {}
            for cur_lang in langs:
                for i, (seg_lang, seg_text) in enumerate(segments):
                    if seg_lang == cur_lang:
                        pcm_by_index[i] = self._synthesize_segment_pcm(seg_text, seg_lang)
            gc.collect()

        pause = b"\x00" * (int(TARGET_SAMPLE_RATE * SEGMENT_PAUSE_SEC) * TARGET_SAMPWIDTH)
        chunks = []
        for i in range(len(segments)):
            pcm = pcm_by_index.get(i)
            if not pcm:
                continue
            if chunks:
                chunks.append(pause)
            chunks.append(pcm)

        if not chunks:
            raise ValueError("تولید صدا نتیجه‌ای نداشت (متن قابل خواندن نبود).")
        return self._pcm_to_wav(b"".join(chunks))

    def synthesize_to_file(self, text: str, out_path: str, lang: str = None) -> str:
        with open(out_path, "wb") as f:
            f.write(self.synthesize_to_bytes(text, lang=lang))
        return out_path


def download_all_models():
    """همه‌ی مدل‌های صوتی را دانلود می‌کند (بدون لود در رم). در زمان build داکر اجرا می‌شود
    تا سرور هنگام بالا آمدن مجبور به دانلود نباشد."""
    engine = AhaTTSEngine(preload=())
    for lang in VOICE_SOURCES:
        engine._ensure_model_files(lang)
        print(f"model ready: {lang}")


if __name__ == "__main__":
    engine = AhaTTSEngine()
    engine.synthesize_to_file("سلام (دنیا)! این یک تست Google Maps است.", "test.wav")
    print("فایل تست ساخته شد: test.wav")
