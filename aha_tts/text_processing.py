"""
پردازش متن قبل از تبدیل به صدا
--------------------------------
- پاک‌سازی نمادها و ایموجی‌ها (پرانتز و ... تبدیل به مکث می‌شوند، خوانده نمی‌شوند)
- یکدست‌سازی حروف فارسی/عربی و حذف اعراب
- تبدیل عدد به حروف فارسی (۱۲۳ -> صد و بیست و سه)
- جداسازی بخش‌های فارسی و انگلیسی تا هرکدام با صدای مناسب خوانده شوند
"""

import re
import unicodedata

PERSIAN_LETTER_RE = re.compile(r"[\u0600-\u06FF]")

# ---------------------------------------------------------------- اعداد

_ONES = ["صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
_TEENS = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده",
          "شانزده", "هفده", "هجده", "نوزده"]
_TENS = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
_HUNDREDS = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد",
             "ششصد", "هفتصد", "هشتصد", "نهصد"]
_SCALES = ["", "هزار", "میلیون", "میلیارد", "تریلیون", "کوادریلیون"]

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _three_digits(n: int) -> str:
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if r:
        if r < 10:
            parts.append(_ONES[r])
        elif r < 20:
            parts.append(_TEENS[r - 10])
        else:
            t, o = divmod(r, 10)
            parts.append(_TENS[t])
            if o:
                parts.append(_ONES[o])
    return " و ".join(parts)


def int_to_persian_words(n: int) -> str:
    if n == 0:
        return "صفر"
    groups = []
    while n > 0:
        n, g = divmod(n, 1000)
        groups.append(g)
    parts = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if not g:
            continue
        if idx == 0:
            parts.append(_three_digits(g))
        elif idx == 1 and g == 1:
            parts.append("هزار")
        else:
            parts.append(_three_digits(g) + " " + _SCALES[idx])
    return " و ".join(parts)


def _int_str_to_words(s: str) -> str:
    # اعداد خیلی بلند یا با صفر ابتدایی (مثل شماره تلفن) رقم‌به‌رقم خوانده می‌شوند
    if len(s) > 15 or (len(s) > 1 and s[0] == "0"):
        return " ".join(_ONES[int(d)] for d in s)
    return int_to_persian_words(int(s))


def number_token_to_words(tok: str) -> str:
    if "." in tok:
        ip, fp = tok.split(".", 1)
        return (_int_str_to_words(ip) + " ممیز "
                + " ".join(_ONES[int(d)] for d in fp))
    return _int_str_to_words(tok)


# ------------------------------------------------------- پاک‌سازی عمومی

_INVISIBLE_RE = re.compile(
    "[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]"
)
_URL_RE = re.compile(r"(?:https?://|www\.)\S+")
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\ufe0f\u2190-\u21FF]"
)
_QUOTES_RE = re.compile("[«»\"“”„‟‘]")


def clean_text(text: str) -> str:
    """پاک‌سازی عمومی: نمادهای خوانده‌نشدنی حذف و علائم به مکث تبدیل می‌شوند."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)  # نیم‌فاصله هم حذف می‌شود (می‌روم -> میروم)
    text = _URL_RE.sub(" ", text)
    text = _EMOJI_RE.sub(" ", text)
    text = re.sub(r"[*#_~`^|\\<>@/]", " ", text)
    text = re.sub(r"[()\[\]{}]", ", ", text)          # پرانتز و ... => مکث
    text = _QUOTES_RE.sub("", text)
    text = re.sub(r"\s[-–—]+\s|[–—]", ", ", text)      # خط تیره => مکث
    text = (text.replace("،", ",").replace("؛", ";")
                .replace("؟", "?").replace("…", "."))
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*([,.;:!?])(?:\s*[,.;:!?])+", r"\1", text)  # علائم پشت‌سرهم
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"^[\s,.;:!?]+", "", text)
    return text.strip()


# ------------------------------------------------------ نرمال‌سازی فارسی

_AR_TO_FA = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه",
    "أ": "ا", "إ": "ا", "ؤ": "و",
})
_DIACRITICS_RE = re.compile("[\u064B-\u065F\u0670\u0640]")


def normalize_persian(text: str) -> str:
    text = text.translate(_DIGIT_MAP).translate(_AR_TO_FA)
    text = _DIACRITICS_RE.sub("", text)
    text = text.replace("٫", ".")
    text = re.sub(r"(?<=\d)[,٬](?=\d{3}(?!\d))", "", text)  # 1,234 -> 1234
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*[%٪]",
        lambda m: " " + number_token_to_words(m.group(1)) + " درصد ",
        text,
    )
    text = re.sub(
        r"\d+(?:\.\d+)?",
        lambda m: " " + number_token_to_words(m.group(0)) + " ",
        text,
    )
    for sym, word in (("%", " درصد "), ("٪", " درصد "), ("&", " و "),
                      ("+", " به علاوه "), ("=", " مساوی "),
                      ("$", " دلار "), ("€", " یورو "), ("°", " درجه ")):
        text = text.replace(sym, word)
    return re.sub(r"\s+", " ", text).strip()


def normalize_english(text: str) -> str:
    for sym, word in (("%", " percent "), ("&", " and "), ("+", " plus "),
                      ("=", " equals "), ("$", " dollars "), ("€", " euros "),
                      ("°", " degrees ")):
        text = text.replace(sym, word)
    return re.sub(r"\s+", " ", text).strip()


# ------------------------------------------------- جداسازی فارسی/انگلیسی

_LATIN_RUN_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9'’\-]*(?:[ \t]+[A-Za-z][A-Za-z0-9'’\-]*)*)"
)


def _has_content(s: str) -> bool:
    return any(c.isalnum() for c in s)


def split_by_script(text: str):
    """متن را به قطعه‌های (زبان، متن) می‌شکند: لاتین => en، بقیه => fa."""
    parts = _LATIN_RUN_RE.split(text)
    segments = []  # list of [lang, text]
    for i, part in enumerate(parts):
        if not part:
            continue
        is_latin = (i % 2 == 1)
        if is_latin:
            lang = "en"
        elif PERSIAN_LETTER_RE.search(part):
            lang = "fa"
        else:
            # فقط عدد/علامت/فاصله: به قطعه قبلی می‌چسبد
            if segments:
                segments[-1][1] += part
            elif _has_content(part):
                segments.append(["fa", part])
            continue
        if segments and segments[-1][0] == lang:
            segments[-1][1] += part
        else:
            segments.append([lang, part])
    return [(lang, seg) for lang, seg in segments]


def prepare_segments(text: str, lang: str = None):
    """
    خروجی: لیست (زبان، متن نرمال‌شده) آماده برای تولید صدا.
    اگر lang="en" داده شود و متن حروف فارسی نداشته باشد، کل متن انگلیسی خوانده می‌شود.
    """
    text = clean_text(text)
    if not text:
        return []

    if lang == "en" and not PERSIAN_LETTER_RE.search(text):
        raw_segments = [("en", text)]
    else:
        raw_segments = split_by_script(text)

    result = []
    for seg_lang, seg_text in raw_segments:
        if seg_lang == "fa":
            seg_text = normalize_persian(seg_text)
        else:
            seg_text = normalize_english(seg_text)
        if _has_content(seg_text):
            result.append((seg_lang, seg_text))
    return result


# ---------------------------------------------- تکه‌تکه کردن متن‌های بلند

def split_long_text(text: str, max_len: int = 300):
    """
    متن بلند را به تکه‌های حداکثر max_len حرفی می‌شکند (ترجیحاً سر جمله/ویرگول)
    تا مصرف حافظه در هر بار تولید صدا محدود بماند.
    """
    text = text.strip()
    if len(text) <= max_len:
        return [text] if text else []

    pieces = re.split(r"(?<=[.!?;:,])\s+", text)
    chunks, cur = [], ""
    for piece in pieces:
        # تکه‌ی خیلی بلند بدون علامت: روی فاصله‌ها بشکن
        while len(piece) > max_len:
            cut = piece.rfind(" ", 0, max_len)
            if cut <= 0:
                cut = max_len
            head, piece = piece[:cut].strip(), piece[cut:].strip()
            if cur:
                chunks.append(cur); cur = ""
            if head:
                chunks.append(head)
        if not piece:
            continue
        if cur and len(cur) + 1 + len(piece) > max_len:
            chunks.append(cur); cur = piece
        else:
            cur = (cur + " " + piece).strip()
    if cur:
        chunks.append(cur)
    return chunks


# ------------------------------------- شکستن متن به عبارت‌ها (بدون علامت)

# مکث (ثانیه) بعد از هر نوع علامت
PAUSE_COMMA = 0.22
PAUSE_COLON = 0.30
PAUSE_SENTENCE = 0.45

_DELIM_RE = re.compile(r"(\.+(?=\s|$)|[;:!?]+|,(?!\d))")


def _sanitize_phrase(text: str, lang: str) -> str:
    """هر نماد باقی‌مانده را حذف می‌کند تا فقط حرف/عدد به مدل برسد."""
    if lang == "fa":
        text = "".join(c if (c.isalpha() or c.isspace()) else " " for c in text)
    else:
        text = "".join(c if (c.isalnum() or c in " '’-.") else " " for c in text)
    return re.sub(r"\s+", " ", text).strip(" .-'’")


def split_into_phrases(text: str, lang: str):
    """
    متن را سر علامت‌های نگارشی به عبارت‌ها می‌شکند.
    خروجی: لیست (عبارت، مکث_بعد_از_آن). مکث None یعنی علامتی وجود نداشت (آخر قطعه).
    خود علامت‌ها هرگز به مدل صوتی داده نمی‌شوند.
    """
    parts = _DELIM_RE.split(text)
    phrases = []
    # parts: [متن, جداکننده, متن, جداکننده, ..., متن]
    for i in range(0, len(parts), 2):
        phrase = _sanitize_phrase(parts[i], lang)
        delim = parts[i + 1] if i + 1 < len(parts) else None
        if delim is None:
            pause = None
        elif delim.startswith(","):
            pause = PAUSE_COMMA
        elif delim.startswith((";", ":")):
            pause = PAUSE_COLON
        else:
            pause = PAUSE_SENTENCE
        if _has_content(phrase):
            phrases.append((phrase, pause))
        elif phrases and pause is not None:
            # علامتِ بدون متن: مکث قبلی را در صورت بلندتر بودن جایگزین کن
            prev_text, prev_pause = phrases[-1]
            phrases[-1] = (prev_text, max(pause, prev_pause or 0))
    return phrases
