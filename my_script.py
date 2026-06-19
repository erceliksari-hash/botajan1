import os
import re
import logging
from typing import List, Dict, Tuple, Optional
from litellm import completion
import asyncio
import aiohttp

# --- Logging Ayarları ---
logging.basicConfig(
    filename='agent.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Constants ---
CODE_DIR = "generated_code"
FILENAME_PATTERN = r"[\w\-]+\.\w+"
MAX_CONTEXT_LINES = 100
MAX_CONTEXT_FILES = 8

# --- Helper Functions ---
def _get_filepath(filename: str) -> str:
    """Belirtilen dosyaya ait dosya yolunu döndürür"""
    filename = os.path.basename(filename.strip())
    return os.path.join(CODE_DIR, filename)

def _check_filepath_exists(filename: str) -> bool:
    """Belirtilen dosyanın var olup olmadığını kontrol eder"""
    filepath = _get_filepath(filename)
    return os.path.exists(filepath)

def _save_code_to_file(filename: str, code_content: str) -> str:
    """Belirtilen dosyaya kodu kaydeder"""
    filepath = _get_filepath(filename)
    overwriting = _check_filepath_exists(filename)

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

def _read_code_from_file(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Belirtilen dosyadan kod okur"""
    filepath = _get_filepath(filename)

    if not _check_filepath_exists(filename):
        return None, f"❌ Dosya bulunamadı: {filename}"

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read(), None
    except Exception as e:
        logging.error(f"Okuma hatası {filepath}: {e}")
        return None, f"❌ Okuma hatası: {e}"

def _list_generated_files() -> Tuple[List[str], Optional[str]]:
    """Tüm oluşturulmuş dosyaları listeler"""
    try:
        files = [f for f in os.listdir(CODE_DIR) if os.path.isfile(os.path.join(CODE_DIR, f))]
        return sorted(files), None
    except Exception as e:
        logging.error(f"Listeleme hatası: {e}")
        return [], f"❌ Hata: {e}"

def _delete_file(filename: str) -> str:
    """Belirtilen dosyayı siler"""
    filepath = _get_filepath(filename)

    try:
        os.remove(filepath)
        logging.info(f"Dosya silindi: {filepath}")
        return f"🗑️ '{filename}' silindi."
    except Exception as e:
        logging.error(f"Silme hatası {filepath}: {e}")
        return f"❌ Hata: '{filename}' silinemedi: {e}"

def _extract_file_summary(filepath: str) -> str:
    """Dosya içeriğinden kısa bir özet çıkarır"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(4000)
    except Exception:
        return "(okunamadı)"

    if filepath.endswith(".py"):
        names = re.findall(r"^(?:def|class)\s+(\w+)", content, re.MULTILINE)
        if names:
            summary = "tanımlar: " + ", ".join(names[:6])
            if len(names) > 6:
                summary += f" (+{len(names) - 6} daha)"
            return summary[:90]

        doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if doc_match:
            return doc_match.group(1).strip().splitlines()[0][:90]
        return "(boş veya betik kodu)"
    else:
        for line in content.splitlines():
            line = line.strip()
            if line:
                return line[:90]
        return "(boş dosya)"

def _get_project_context() -> str:
    """Proje bağlamını döndürür"""
    try:
        files = sorted(f for f in os.listdir(CODE_DIR) if f.endswith(('.py', '.js', '.md', '.txt')))
    except Exception as e:
        logging.error(f"get_project_context hatası: {e}")
        return "Proje dosyaları okunamadı."

    if not files:
        return "Projede başka dosya yok."

    icon_map = {".py": "🐍", ".js": "📜", ".md": "📘", ".txt": "📄"}
    lines = [f"generated_code/  ({len(files)} dosya)"]

    for f in files[:8]:
        ext = os.path.splitext(f)[1]
        icon = icon_map.get(ext, "📄")
        summary = _extract_file_summary(os.path.join(CODE_DIR, f))
        lines.append(f"  ├─ {icon} {f} — {summary}")

    if len(files) > 8:
        lines.append(f"  └─ ... ve {len(files) - 8} dosya daha.")

    return "Proje yapısı:\n" + "\n".join(lines)

# --- Unified LLM Interface ---
class UnifiedLLM:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.api_key = os.getenv(config.api_key_env_var)
        if not self.api_key:
            raise ValueError(f"API key not found for {config.name}")

    async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> str:
        try:
            response = completion(
                model=self.config.model_name or self.config.name,
                messages=messages,
                api_key=self.api_key,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"LLM error for {self.config.name}: {e}")
            return f"❌ Hata: {str(e)}"

    def get_model_name(self) -> str:
        return self.config.name

# --- Model Configuration ---
class ModelConfig:
    def __init__(self, name: str, api_key_env_var: str, base_url: Optional[str] = None, model_name: Optional[str] = None):
        self.name = name
        self.api_key_env_var = api_key_env_var
        self.base_url = base_url
        self.model_name = model_name
