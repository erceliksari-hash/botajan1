import streamlit as st
import os
import logging
import re
from typing import List, Dict, Tuple, Optional
from litellm import completion

# --- Logging Ayarları ---
logging.basicConfig(filename='agent.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
os.environ["HF_TOKEN"] = st.secrets.get("HF_TOKEN", os.environ.get("HF_TOKEN", ""))
CODE_DIR = "generated_code"
os.makedirs(CODE_DIR, exist_ok=True)

# --- Session State Init ---
def init_session_state():
    defaults = {
        "messages": [],
        "selected_file_for_revision": None,
        "loaded_file_content": "",
        "pending_code_to_save": None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# --- Helper Functions ---
def save_code_to_file(filename: str, code_content: str) -> str:
    try:
        filepath = os.path.join(CODE_DIR, os.path.basename(filename.strip()))
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code_content)
        return f"✅ '{filename}' başarıyla kaydedildi."
    except Exception as e:
        return f"❌ Hata: {e}"

def get_project_context() -> str:
    files = sorted(f for f in os.listdir(CODE_DIR) if f.endswith(('.py', '.js', '.md', '.txt')))
    if not files: return "Projede başka dosya yok."
    
    icon_map = {".py": "🐍", ".js": "📜", ".md": "📝", ".txt": "📄"}
    lines = ["Projedeki dosyalar:"]
    for f in files[:8]:
        icon = icon_map.get(os.path.splitext(f)[1], "📁")
        lines.append(f"  ├─ {icon} {f}")
    return "\n".join(lines)

# --- CodingAgent Class ---
class CodingAgent:
    def __init__(self, model_name="huggingface/meta-llama/Llama-3.3-70B-Instruct"):
        self.model_name = model_name

    def process(self, user_input: str) -> str:
        try:
            context = get_project_context()
            messages = [{"role": "system", "content": f"Sen bir kodlama asistanısın. Context: {context}"}] + st.session_state.messages
            response = completion(model=self.model_name, messages=messages)
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"LLM Hatası: {e}")
            return f"❌ Model yanıt veremedi: {e}"

# --- UI ---
st.set_page_config(page_title="Pro-Coding Agent", layout="wide")
init_session_state()
agent = CodingAgent()

st.title("🚀 Pro-Coding Agent")

# Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
if prompt := st.chat_input("Kodlama komutunuzu girin..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    
    with st.spinner("Ajan düşünüyor..."):
        response = agent.process(prompt)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

# SideBar - File Management
with st.sidebar:
    st.header("Dosyalar")
    files, _ = list_generated_files() # list_generated_files fonksiyonunu yukarıdaki gibi tanımlayabilirsin
    for f in files:
        st.text(f)
