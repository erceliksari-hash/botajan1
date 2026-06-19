import streamlit as st
import os
import logging
import datetime
import re
from typing import List, Dict, Tuple, Optional
from litellm import completion

# --- Logging Ayarları ---
logging.basicConfig(
    filename='agent.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Configuration ---
if "HF_TOKEN" not in os.environ and "HUGGINGFACE_API_KEY" in os.environ:
    os.environ["HF_TOKEN"] = os.environ["HUGGINGFACE_API_KEY"]
try:
    if "HF_TOKEN" not in os.environ and "HF_TOKEN" in st.secrets:
        os.environ["HF_TOKEN"] = st.secrets["HF_TOKEN"]
except Exception:
    pass

CODE_DIR = "generated_code"
if not os.path.exists(CODE_DIR):
    os.makedirs(CODE_DIR)

# Dosya adı geçerlilik kuralı: harf, rakam, alt çizgi, tire, nokta (boşluk/garip karakter yok)
FILENAME_PATTERN = r"[\w\-]+\.\w+"
MAX_CONTEXT_LINES = 100  # Prompt'a eklenirken büyük dosyaları özetlemek için sınır


# --- Session State ---
def init_session_state():
    defaults = {
        "messages": [],
        "selected_file_for_revision": None,
        "loaded_file_content": "",
        "pending_code_to_save": None,
        "agent": None,  # CodingAgent örneği burada saklanacak (her rerun'da yeniden oluşturmamak için)
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# --- Helper Functions ---
def save_code_to_file(filename: str, code_content: str) -> str:
    filename = os.path.basename(filename.strip())
    filepath = os.path.join(CODE_DIR, filename)
    overwriting = os.path.exists(filepath)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code_content)
        logging.info(f"Dosya {'üzerine yazıldı' if overwriting else 'kaydedildi'}: {filepath}")
        if overwriting:
            return f"♻️ '{filename}' zaten vardı, içeriği güncellendi (üzerine yazıldı)."
        return f"✅ '{filename}' başarıyla kaydedildi."
    except Exception as e:
        logging.error(f"Dosya kaydetme hatası {filepath}: {e}")
        return f"❌ Hata: {e}"


def read_code_from_file(filename: str) -> Tuple[Optional[str], Optional[str]]:
    filename = os.path.basename(filename.strip())
    filepath = os.path.join(CODE_DIR, filename)
    if not os.path.exists(filepath):
        return None, f"❌ Dosya bulunamadı: {filename}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read(), None
    except Exception as e:
        logging.error(f"Okuma hatası {filepath}: {e}")
        return None, f"❌ Okuma hatası: {e}"


def list_generated_files() -> Tuple[List[str], Optional[str]]:
    try:
        files = [f for f in os.listdir(CODE_DIR) if os.path.isfile(os.path.join(CODE_DIR, f))]
        return sorted(files), None
    except Exception as e:
        logging.error(f"Listeleme hatası: {e}")
        return [], f"❌ Hata: {e}"


def delete_file(filename: str) -> str:
    filename = os.path.basename(filename.strip())
    filepath = os.path.join(CODE_DIR, filename)
    try:
        os.remove(filepath)
        logging.info(f"Dosya silindi: {filepath}")
        return f"🗑️ '{filename}' silindi."
    except Exception as e:
        logging.error(f"Silme hatası {filepath}: {e}")
        return f"❌ Hata: '{filename}' silinemedi: {e}"


MAX_CONTEXT_FILES = 8       # Context'e dahil edilecek maks. dosya sayısı
MAX_SUMMARY_CHARS = 90      # Her dosya özeti için karakter sınırı


def _extract_file_summary(filepath: str) -> str:
    """
    Bir dosyanın içeriğine kısa bir göz atar ve LLM'in dosyanın ne işe
    yaradığını anlamasına yardımcı olacak tek satırlık bir özet üretir.
    Tüm içeriği context'e basmak yerine (token israfı) bu yeterli olur.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(4000)  # Dosyanın başından küçük bir parça yeterli
    except Exception:
        return "(okunamadı)"

    if filepath.endswith(".py"):
        # Üst seviye fonksiyon/sınıf adlarını çıkar
        names = re.findall(r"^(?:def|class)\s+(\w+)", content, re.MULTILINE)
        if names:
            summary = "tanımlar: " + ", ".join(names[:6])
            if len(names) > 6:
                summary += f" (+{len(names) - 6} daha)"
            return summary[:MAX_SUMMARY_CHARS]
        # Fonksiyon/sınıf yoksa dosyanın başındaki docstring veya yorumu dene
        doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if doc_match:
            return doc_match.group(1).strip().splitlines()[0][:MAX_SUMMARY_CHARS]
        return "(boş veya betik kodu)"
    else:
        # .md / .txt / .js gibi diğer dosyalar için ilk anlamlı satırı al
        for line in content.splitlines():
            line = line.strip()
            if line:
                return line[:MAX_SUMMARY_CHARS]
        return "(boş dosya)"


def get_project_context() -> str:
    """
    Klasördeki dosyaları bir 'dosya ağacı' + kısa içerik özeti olarak döndürür.
    Bu sayede LLM, sadece dosya adlarını değil her dosyanın ne işe yaradığını da görür.
    Token maliyetini sınırlamak için dosya sayısı ve özet uzunluğu kısıtlanır.
    """
    try:
        files = sorted(f for f in os.listdir(CODE_DIR) if f.endswith(('.py', '.js', '.md', '.txt')))
    except Exception as e:
        logging.error(f"get_project_context hatası: {e}")
        return "Proje dosyaları okunamadı."

    if not files:
        return "Projede başka dosya yok."

    icon_map = {
