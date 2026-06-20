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

# --- Helper Functions ---
def save_code_to_file(filename: str, code_content: str) -> str:
    filename = os.path.basename(filename.strip())
    filepath = os.path.join(CODE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code_content)
    return f"✅ '{filename}' başarıyla kaydedildi."

def read_code_from_file(filename: str) -> Tuple[Optional[str], Optional[str]]:
    filename = os.path.basename(filename.strip())
    filepath = os.path.join(CODE_DIR, filename)
    if not os.path.exists(filepath):
        return None, f"❌ Dosya bulunamadı: {filename}"
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read(), None

def list_generated_files() -> Tuple[List[str], Optional[str]]:
    files = [f for f in os.listdir(CODE_DIR) if os.path.isfile(os.path.join(CODE_DIR, f))]
    return sorted(files), None

def _extract_file_summary(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(2000)
        if filepath.endswith(".py"):
            names = re.findall(r"^(?:def|class)\s+(\w+)", content, re.MULTILINE)
            return ("tanımlar: " + ", ".join(names[:4])) if names else "(py dosyası)"
        return "dosya içeriği mevcut"
    except:
        return "(okunamadı)"

def get_project_context() -> str:
    files = sorted(f for f in os.listdir(CODE_DIR) if f.endswith(('.py', '.js', '.md', '.txt')))
    if not files: return "Projede başka dosya yok."
    
    icon_map = {".py": "🐍", ".js": "📜", ".md": "📝", ".txt": "📄"}
    lines = ["Projedeki diğer dosyalar:"]
    for f in files[:8]:
        icon = icon_map.get(os.path.splitext(f)[1], "📁")
        summary = _extract_file_summary(os.path.join(CODE_DIR, f))
        lines.append(f"  ├─ {icon} {f} — {summary}")
    return "\n".join(lines)

# --- AI Integration ---
def get_llm_response(prompt_messages, model_name, **kwargs):
    return completion(model=model_name, messages=prompt_messages, **kwargs).choices[0].message.content

# --- Main App ---
st.set_page_config(page_title="Pro-Coding Agent", layout="wide")
if "messages" not in st.session_state: st.session_state.messages = []

st.title("🚀 Pro-Coding Agent")

# Chat UI
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Kodlama komutunuzu girin..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    
    with st.spinner("Ajan çalışıyor..."):
        # Basit bir prompt hazırlığı
        context = get_project_context()
        sys_msg = f"Sen bir kodlama asistanısın. {context}"
        messages = [{"role": "system", "content": sys_msg}] + st.session_state.messages
        
        try:
            response = get_llm_response(messages, "huggingface/meta-llama/Llama-3.3-70B-Instruct")
            st.session_state.messages.append({"role": "assistant", "content": response})
            st.rerun()
        except Exception as e:
            st.error(f"Hata: {e}")
