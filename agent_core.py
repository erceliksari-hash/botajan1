"""
agent_core.py
--------------
Streamlit'e bağımlılığı OLMAYAN saf iş mantığı katmanı:
dosya işlemleri, proje bağlamı çıkarımı, LLM çağrısı ve komut ayrıştırma.

Bu modül bilerek `streamlit` import ETMEZ; böylece CLI, test veya
başka bir arayüz (FastAPI, Tkinter vb.) ile de yeniden kullanılabilir.
UI'a özgü her şey (st.secrets, st.session_state, st.rerun) app.py'da kalır.
"""

import os
import re
import logging
import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from litellm import completion

# --- Logging Ayarları ---
logging.basicConfig(
    filename="agent.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# --- Constants ---
CODE_DIR = "generated_code"
FILENAME_PATTERN = r"[\w\-]+\.\w+"          # harf/rakam/_/- ve bir uzantı; boşluksuz
ALLOWED_EXTENSIONS = (".py", ".js", ".md", ".txt")
MAX_CONTEXT_LINES = 100                      # Prompt'a giderken dosya özetleme sınırı
MAX_CONTEXT_FILES = 8                        # Proje bağlamına dahil edilecek maks. dosya
MAX_SUMMARY_CHARS = 90                       # Her dosya özeti için karakter sınırı

os.makedirs(CODE_DIR, exist_ok=True)


def setup_environment():
    """
    Ortam değişkenlerini normalize eder (sadece os.environ üzerinden).
    Not: st.secrets okuma işi Streamlit'e özgü olduğu için app.py'da yapılır;
    bu fonksiyon yalnızca HUGGINGFACE_API_KEY -> HF_TOKEN takma adını kurar.
    """
    if "HF_TOKEN" not in os.environ and "HUGGINGFACE_API_KEY" in os.environ:
        os.environ["HF_TOKEN"] = os.environ["HUGGINGFACE_API_KEY"]


def has_hf_token() -> bool:
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY"))


# litellm model öneki -> gerekli ortam değişkeni eşlemesi.
# "Yapay zeka kardeşler" farklı sağlayıcılardan geldiği için her birinin
# kendi API key'i gerekir; bu eşleme hangi key'in eksik olduğunu söylememizi sağlar.
PROVIDER_KEY_MAP = {
    "huggingface/": ("HF_TOKEN", "Hugging Face"),
    "anthropic/": ("ANTHROPIC_API_KEY", "Anthropic (Claude)"),
    "openai/": ("OPENAI_API_KEY", "OpenAI (GPT)"),
    "gemini/": ("GEMINI_API_KEY", "Google (Gemini)"),
}


def required_api_key_env(model_name: str) -> Optional[Tuple[str, str]]:
    """Model adının önekine göre gereken ortam değişkenini ve sağlayıcı adını döndürür."""
    for prefix, (env_name, provider_label) in PROVIDER_KEY_MAP.items():
        if model_name.startswith(prefix):
            return env_name, provider_label
    return None  # Tanınmayan önek - litellm kendi hata mesajını verir


def has_required_key(model_name: str) -> bool:
    """Seçilen model için gerekli API key'in ortamda olup olmadığını kontrol eder."""
    req = required_api_key_env(model_name)
    if req is None:
        return True
    env_name, _ = req
    if env_name == "HF_TOKEN":
        return has_hf_token()
    return bool(os.environ.get(env_name))


def is_valid_filename(filename: str) -> bool:
    """Dosya adının güvenli ve beklenen formatta olup olmadığını kontrol eder."""
    return bool(re.fullmatch(FILENAME_PATTERN, filename.strip()))


def _resolve_path(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Dosya adını doğrular ve güvenli bir tam yola çevirir.
    Hem regex doğrulaması hem de os.path.basename ile çift katmanlı koruma sağlar
    (path traversal: '../../etc/passwd' gibi girişimlere karşı).
    """
    cleaned = os.path.basename(filename.strip())
    if not is_valid_filename(cleaned):
        return None, (
            f"❌ Geçersiz dosya adı: '{filename}'. "
            "Sadece harf, rakam, `_`, `-`, `.` kullanın (örn: app.py)."
        )
    return os.path.join(CODE_DIR, cleaned), None


# --- Dosya İşlemleri ---
def save_code_to_file(filename: str, code_content: str) -> str:
    filepath, error = _resolve_path(filename)
    if error:
        logging.warning(f"Geçersiz dosya adıyla kaydetme denemesi: {filename}")
        return error

    overwriting = os.path.exists(filepath)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code_content)
        logging.info(f"Dosya {'üzerine yazıldı' if overwriting else 'kaydedildi'}: {filepath}")
        if overwriting:
            return f"♻️ '{os.path.basename(filepath)}' zaten vardı, içeriği güncellendi (üzerine yazıldı)."
        return f"✅ '{os.path.basename(filepath)}' başarıyla kaydedildi."
    except Exception as e:
        logging.error(f"Dosya kaydetme hatası {filepath}: {e}")
        return f"❌ Hata: {e}"


def read_code_from_file(filename: str) -> Tuple[Optional[str], Optional[str]]:
    filepath, error = _resolve_path(filename)
    if error:
        return None, error
    if not os.path.exists(filepath):
        return None, f"❌ Dosya bulunamadı: {os.path.basename(filepath)}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read(), None
    except Exception as e:
        logging.error(f"Okuma hatası {filepath}: {e}")
        return None, f"❌ Okuma hatası: {e}"


def delete_file(filename: str) -> str:
    filepath, error = _resolve_path(filename)
    if error:
        return error
    try:
        os.remove(filepath)
        logging.info(f"Dosya silindi: {filepath}")
        return f"🗑️ '{os.path.basename(filepath)}' silindi."
    except FileNotFoundError:
        return f"❌ Dosya bulunamadı: {os.path.basename(filepath)}"
    except Exception as e:
        logging.error(f"Silme hatası {filepath}: {e}")
        return f"❌ Hata: '{os.path.basename(filepath)}' silinemedi: {e}"


def list_generated_files() -> Tuple[List[str], Optional[str]]:
    try:
        files = [f for f in os.listdir(CODE_DIR) if os.path.isfile(os.path.join(CODE_DIR, f))]
        return sorted(files), None
    except Exception as e:
        logging.error(f"Listeleme hatası: {e}")
        return [], f"❌ Hata: {e}"


# --- Proje Bağlamı (dosya ağacı + özet) ---
def _extract_file_summary(filepath: str) -> str:
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
            return summary[:MAX_SUMMARY_CHARS]
        doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if doc_match:
            return doc_match.group(1).strip().splitlines()[0][:MAX_SUMMARY_CHARS]
        return "(boş veya betik kodu)"

    for line in content.splitlines():
        line = line.strip()
        if line:
            return line[:MAX_SUMMARY_CHARS]
    return "(boş dosya)"


def get_project_context() -> str:
    """Proje klasörünü 'dosya ağacı + içerik özeti' olarak döndürür (LLM'e bağlam için)."""
    try:
        files = sorted(f for f in os.listdir(CODE_DIR) if f.endswith(ALLOWED_EXTENSIONS))
    except Exception as e:
        logging.error(f"get_project_context hatası: {e}")
        return "Proje dosyaları okunamadı."

    if not files:
        return "Projede başka dosya yok."

    icon_map = {".py": "🐍", ".js": "📜", ".md": "📘", ".txt": "📄"}
    lines = [f"generated_code/  ({len(files)} dosya)"]
    for f in files[:MAX_CONTEXT_FILES]:
        ext = os.path.splitext(f)[1]
        icon = icon_map.get(ext, "📄")
        summary = _extract_file_summary(os.path.join(CODE_DIR, f))
        lines.append(f"  ├─ {icon} {f} — {summary}")

    if len(files) > MAX_CONTEXT_FILES:
        lines.append(f"  └─ ... ve {len(files) - MAX_CONTEXT_FILES} dosya daha.")

    return "Proje yapısı:\n" + "\n".join(lines)


def summarize_for_prompt(content: str, max_lines: int = MAX_CONTEXT_LINES) -> str:
    """Büyük dosyaları LLM'e gönderirken baş/son satırlarla özetler (token tasarrufu)."""
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content
    half = max_lines // 2
    head, tail = "\n".join(lines[:half]), "\n".join(lines[-half:])
    omitted = len(lines) - max_lines
    return f"{head}\n\n# ... [{omitted} satır kısaltıldı] ...\n\n{tail}"


# --- LLM Entegrasyonu ---
def get_llm_response(prompt_messages: List[Dict[str, str]], model_name: str, **kwargs) -> str:
    if not has_required_key(model_name):
        req = required_api_key_env(model_name)
        env_name, provider_label = req if req else ("?", "bilinmeyen sağlayıcı")
        logging.warning(f"{env_name} ayarlı değil, çağrı engellendi ({provider_label}).")
        return f"❌ Hata: '{provider_label}' için `{env_name}` ayarlı değil."
    try:
        logging.info(f"LLM çağrısı yapılıyor: {model_name} | kwargs={kwargs}")
        response = completion(model=model_name, messages=prompt_messages, **kwargs)
        content = response.choices[0].message.content
        logging.info(f"LLM yanıtı alındı ({len(content)} karakter).")
        return content
    except Exception as e:
        error_msg = f"Model yanıt veremedi: {e}"
        logging.error(error_msg)
        return f"❌ {error_msg}"


# --- Komut Sonucu (UI'a dönen veri sözleşmesi) ---
@dataclass
class CommandResult:
    assistant_message: str
    file_state_changed: bool = False           # selected_file/loaded_content değişti mi?
    selected_file: Optional[str] = None         # None = revizyon modunu kapat
    loaded_content: str = ""
    pending_save: Optional[Dict[str, str]] = None  # {"filename":..., "content":...}


# --- Komut Ayrıştırma Regex'leri ---
_SAVE_RE = rf"\bkaydet\s+({FILENAME_PATTERN})(?:\s*:\s*(.*))?"
_READ_RE = rf"\boku\s+({FILENAME_PATTERN})"
_REVISE_RE = rf"\brevize et\s+({FILENAME_PATTERN})"
_DELETE_RE = rf"\bsil\s+({FILENAME_PATTERN})"
_LIST_RE = r"\bdosyaları listele\b"
_CODE_BLOCK_RE = r"```(?:\w+)?\n(.*?)```"


class CodingAgent:
    """
    Kodlama ajanı orkestratörü.
    NOT: Bu sınıf `streamlit` veya `st.session_state`'e dokunmaz. Sohbet geçmişi,
    revizyon dosyası ve içeriği parametre olarak alınır; sonuç olarak bir
    `CommandResult` döner. UI tarafı (app.py) bu sonucu kendi state'ine uygular.
    """

    def __init__(self, model_name: str, temperature: float = 0.7, max_tokens: int = 1500):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    def update_params(self, model_name: str, temperature: float, max_tokens: int):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _build_prompt(
        self,
        user_input: str,
        history: List[Dict[str, str]],
        selected_file: Optional[str],
        loaded_content: str,
    ) -> List[Dict[str, str]]:
        system_message = (
            "Sen profesyonel bir kodlama ajanısın. "
            f"{get_project_context()}\n"
            "Sadece temiz, çalışabilir kod üret. Kod bloklarını markdown formatında "
            "(```python ... ```) ver. Bir dosya revize ediliyorsa, dosyanın TÜM içeriğini "
            "tekrar ver, sadece değişen kısmı değil. Dosya adlarında her zaman uzantı kullan."
        )
        messages = [{"role": "system", "content": system_message}]
        messages += [m for m in history if m["role"] in ("user", "assistant")]

        if selected_file and loaded_content:
            messages.append({
                "role": "user",
                "content": (
                    f"Şu an üzerinde çalıştığımız dosya ('{selected_file}'):\n"
                    f"```\n{summarize_for_prompt(loaded_content)}\n```\n"
                    "Bu dosyayı aşağıdaki talimata göre güncelle ve TÜM kodu tekrar ver."
                ),
            })
        messages.append({"role": "user", "content": user_input})
        return messages

    def process_command(
        self,
        user_input: str,
        history: List[Dict[str, str]],
        selected_file: Optional[str],
        loaded_content: str,
    ) -> CommandResult:
        """
        Kullanıcı girdisini işler ve bir CommandResult döner.
        `history` SADECE okunur; bu fonksiyon hiçbir listeyi/state'i mutasyona uğratmaz.
        """
        logging.info(f"Komut alındı: {user_input[:120]}")

        save_match = re.search(_SAVE_RE, user_input, re.DOTALL | re.IGNORECASE)
        read_match = re.search(_READ_RE, user_input, re.IGNORECASE)
        revise_match = re.search(_REVISE_RE, user_input, re.IGNORECASE)
        delete_match = re.search(_DELETE_RE, user_input, re.IGNORECASE)
        list_match = re.search(_LIST_RE, user_input, re.IGNORECASE)

        if save_match:
            filename, code = save_match.group(1).strip(), save_match.group(2)
            if code:
                msg = save_code_to_file(filename, code.strip())
                return CommandResult(msg, file_state_changed=True, selected_file=None, loaded_content="")
            return CommandResult(
                f"'{filename}' için kaydedilecek kod içeriği belirtilmedi. "
                f"`kaydet <dosya_adı>: <kod>` şeklinde girin veya önce bir AI çıktısı üretin."
            )

        if delete_match:
            filename = delete_match.group(1).strip()
            msg = delete_file(filename)
            if selected_file == filename:
                return CommandResult(msg, file_state_changed=True, selected_file=None, loaded_content="")
            return CommandResult(msg)

        if read_match:
            filename = read_match.group(1).strip()
            content, error = read_code_from_file(filename)
            if error:
                return CommandResult(error)
            preview = summarize_for_prompt(content, max_lines=60)
            msg = f"'{filename}' yüklendi ve düzenleme için hazır:\n```\n{preview}\n```"
            return CommandResult(msg, file_state_changed=True, selected_file=filename, loaded_content=content)

        if revise_match:
            filename = revise_match.group(1).strip()
            content, error = read_code_from_file(filename)
            if error:
                return CommandResult(error)
            msg = f"'{filename}' revize edilmek üzere yüklendi. Şimdi talimatlarınızı girin."
            return CommandResult(msg, file_state_changed=True, selected_file=filename, loaded_content=content)

        if list_match:
            files, error = list_generated_files()
            if error:
                return CommandResult(error)
            msg = "Mevcut dosyalar: " + ", ".join(files) if files else "Henüz kaydedilmiş dosya bulunmuyor."
            return CommandResult(msg)

        # --- Genel AI üretimi ---
        prompt_messages = self._build_prompt(user_input, history, selected_file, loaded_content)
        llm_response = get_llm_response(
            prompt_messages, self.model_name, temperature=self.temperature, max_tokens=self.max_tokens
        )

        code_blocks = re.findall(_CODE_BLOCK_RE, llm_response, re.DOTALL)
        pending_save = None
        if code_blocks:
            filename_to_suggest = selected_file or f"code_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
            pending_save = {"filename": filename_to_suggest, "content": code_blocks[-1]}

        return CommandResult(llm_response, pending_save=pending_save)
