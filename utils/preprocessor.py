# utils/preprocessor.py
# Pipeline preprocessing dari kode skripsi — diintegrasikan ke Flask

import re
import sys
import os

# ── Load kamus langsung dari path absolut (aman di semua OS) ──────────
import importlib.util

def _load_kamus():
    kamus_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'kamus_normalisasi.py')
    spec   = importlib.util.spec_from_file_location('kamus_normalisasi', kamus_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_kamus = _load_kamus()
KAMUS_NORMALISASI   = _kamus.KAMUS_NORMALISASI
KATA_KUNCI_KEPUASAN = _kamus.KATA_KUNCI_KEPUASAN
STOPWORD_TAMBAHAN   = _kamus.STOPWORD_TAMBAHAN
KATA_LINDUNGI       = _kamus.KATA_LINDUNGI

from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory

# ── Inisialisasi Sastrawi (sekali saja) ──────────────────────────────
_stemmer          = None
_stopword_remover = None

def _get_stemmer():
    global _stemmer
    if _stemmer is None:
        _stemmer = StemmerFactory().create_stemmer()
    return _stemmer

def _get_stopword_remover():
    global _stopword_remover
    if _stopword_remover is None:
        _stopword_remover = StopWordRemoverFactory().create_stop_word_remover()
    return _stopword_remover

# ── Pola Emoji ────────────────────────────────────────────────────────
EMOJI_PATTERN = re.compile(
    '[' +
    u'\U0001F600-\U0001F64F'
    u'\U0001F300-\U0001F5FF'
    u'\U0001F680-\U0001F6FF'
    u'\U0001F700-\U0001F77F'
    u'\U0001F780-\U0001F7FF'
    u'\U0001F800-\U0001F8FF'
    u'\U0001F900-\U0001F9FF'
    u'\U0001FA00-\U0001FA6F'
    u'\U0001FA70-\U0001FAFF'
    u'\U00002702-\U000027B0'
    u'\U000024C2-\U0001F251'
    u'\U0001f926-\U0001f937'
    u'\U00010000-\U0010ffff'
    u'\u2640-\u2642'
    u'\u2600-\u2B55'
    u'\u200d\u23cf\u23e9\u231a\ufe0f\u3030'
    u'\u00a9\u00ae'
    + ']',
    flags=re.UNICODE
)

# ── Tahapan (sama persis dengan kode skripsi) ─────────────────────────

def step_cleaning(teks: str) -> str:
    teks = str(teks)
    teks = re.sub(r'http\S+|www\S+', '', teks)
    teks = EMOJI_PATTERN.sub(' ', teks)
    teks = re.sub(r'[^a-zA-Z0-9\s]', ' ', teks)
    teks = re.sub(r'\s+', ' ', teks).strip()
    return teks

def step_case_folding(teks: str) -> str:
    return teks.lower()

def step_normalisasi(teks: str) -> str:
    return ' '.join(KAMUS_NORMALISASI.get(k, k) for k in teks.split())

def step_tokenisasi(teks: str) -> list:
    # split() setara word_tokenize untuk teks Indonesia bersih
    return teks.split()

def step_hapus_stopword(tokens: list) -> list:
    remover = _get_stopword_remover()
    teks    = remover.remove(' '.join(tokens))
    return [k for k in teks.split() if k not in STOPWORD_TAMBAHAN and len(k) > 1]

def step_stemming(tokens: list) -> list:
    stemmer = _get_stemmer()
    return [k if k in KATA_LINDUNGI else stemmer.stem(k) for k in tokens]

def mengandung_kata_kepuasan(teks: str) -> bool:
    teks_lower = str(teks).lower()
    return any(k in teks_lower for k in KATA_KUNCI_KEPUASAN)

# ── Pipeline Utama ────────────────────────────────────────────────────

def preprocess(teks: str) -> dict:
    hasil = {}
    hasil['original']     = teks

    s1 = step_cleaning(teks)
    hasil['cleaning']     = s1

    s2 = step_case_folding(s1)
    hasil['case_folding'] = s2

    s3 = step_normalisasi(s2)
    hasil['slang_norm']   = s3

    tokens                = step_tokenisasi(s3)
    hasil['tokenisasi']   = tokens

    tokens_sw             = step_hapus_stopword(tokens)
    hasil['stopword']     = tokens_sw

    tokens_stem           = step_stemming(tokens_sw)
    hasil['stemming']     = tokens_stem

    hasil['result']       = ' '.join(tokens_stem)
    hasil['relevan']      = mengandung_kata_kepuasan(teks)

    return hasil