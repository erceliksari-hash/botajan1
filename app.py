"""
app.py
------
Streamlit arayüzü. Tüm iş mantığı `agent_core.py`'da yaşar; bu dosya
sadece kullanıcı etkileşimini (girdi, butonlar, sidebar) yönetir ve
agent_core'dan dönen sonuçları st.session_state'e uygular.
"""

import os
from typing import Optional
import streamlit as st

import agent_core as core

# --- Ortam Kurulumu ---
core.setup_environment()


def _load_secret_into_env(env_name: str):
    """st.secrets'tan okur, yoksa dokunmaz. Yerelde .env / Streamlit Cloud'da Secrets çalışır."""
    try:
        if env_name not in os.environ and env_name in st.secrets:
            os.environ[env_name] = st.secrets[env_name]
    except Exception:
        pass


for _env_name in ("HF_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
    _load_secret_into_env(_env_name)


def init_session_state():
    defaults = {
        "messages": [],
        "selected_file_for_revision": None,
        "loaded_file_content": "",
        "pending_code_to_save": None,
        "agent": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


st.set_page_config(page_title="Pro-Coding Agent", layout="wide")
init_session_state()

st.title("🚀 Pro-Coding Agent")

# --- Sidebar ---
with st.sidebar:
    st.header("Ayarlar ve Dosyalar")
    st.subheader("AI Modeli Seçimi")

    # "Yapay zeka kardeşler": her biri farklı bir sağlayıcıdan, farklı bir güçlü yan için.
    # Not: Claude 3 Opus ve GPT-4 Turbo artık güncel değil; yerlerine güncel
    # eşdeğerleri (Claude Sonnet 4.6, GPT-5.4 mini) kullanılıyor.
    available_models = {
        "🦙 Llama 3.3 70B (HF) — hata ayıklama": "huggingface/meta-llama/Llama-3.3-70B-Instruct",
        "🐱 Qwen2.5 Coder 32B (HF) — performans": "huggingface/Qwen/Qwen2.5-Coder-32B-Instruct",
        "⚡ Zephyr 7B Beta (HF) — hızlı analiz": "huggingface/HuggingFaceH4/zephyr-7b-beta",
        "🧠 Claude Sonnet 4.6 (Anthropic) — mimari/kalite": "anthropic/claude-sonnet-4-6",
        "✨ Gemini 3.5 Flash (Google) — bütüncül değerlendirme": "gemini/gemini-3.5-flash",
        "🤖 GPT-5.4 mini (OpenAI) — okunabilirlik": "openai/gpt-5.4-mini",
        "Özel model adı gir...": "custom",
    }
    selected_model_display = st.selectbox("Kullanılacak AI Modeli:", list(available_models.keys()))
    selected_model_name = available_models[selected_model_display]
    if selected_model_name == "custom":
        selected_model_name = st.text_input(
            "Model adı (litellm formatı):",
            value="huggingface/meta-llama/Llama-3.1-8B-Instruct",
        )

    with st.expander("🔑 API Anahtarları (sağlayıcı bazlı)"):
        st.caption("Sadece kullanacağın sağlayıcının anahtarını gir. Boş bırakılanlar dokunulmaz.")
        key_inputs = {
            "HF_TOKEN": "Hugging Face (Llama/Qwen/Zephyr)",
            "ANTHROPIC_API_KEY": "Anthropic (Claude)",
            "OPENAI_API_KEY": "OpenAI (GPT)",
            "GEMINI_API_KEY": "Google (Gemini)",
        }
        for env_name, label in key_inputs.items():
            current = os.environ.get(env_name, "")
            entered = st.text_input(
                f"{label}:", value=current, type="password", key=f"key_input_{env_name}"
            )
            if entered:
                os.environ[env_name] = entered

    with st.expander("⚙️ Gelişmiş Ayarlar"):
        temperature = st.slider("Sıcaklık (yaratıcılık)", 0.0, 1.5, 0.7, 0.1)
        max_tokens = st.slider("Maks. çıktı uzunluğu (token)", 256, 4096, 1500, 128)

    if not core.has_required_key(selected_model_name):
        req = core.required_api_key_env(selected_model_name)
        if req:
            env_name, provider_label = req
            st.warning(f"⚠️ '{provider_label}' için `{env_name}` ayarlanmamış. Yukarıdan ekleyebilirsin.")

    st.info(
        "Örnek komutlar:\n"
        "- `Python'da 'Merhaba Dünya' yazan bir fonksiyon oluştur.`\n"
        "- `kaydet my_script.py: print('Hello world!')`\n"
        "- `oku my_script.py`\n"
        "- `revize et my_script.py`\n"
        "- `sil my_script.py`\n"
        "- `dosyaları listele`\n\n"
        "_Not: dosya adlarında sadece harf, rakam, `_`, `-`, `.` kullanın (boşluksuz)._\n\n"
        "💡 Belirli bir modelden görev bazlı yardım istemek için aşağıdaki "
        "**'🤝 AI Kardeşler'** panelindeki hazır şablonları kullanabilirsin."
    )

    st.subheader("Yüklenmiş Dosya Revizyonu")
    if st.session_state.selected_file_for_revision:
        line_count = len(st.session_state.loaded_file_content.splitlines())
        st.info(f"Revize edilen dosya: **{st.session_state.selected_file_for_revision}** ({line_count} satır)")
        with st.expander("Yüklenen dosya içeriği"):
            st.code(st.session_state.loaded_file_content, language="python")
            if line_count > core.MAX_CONTEXT_LINES:
                st.caption(
                    f"ℹ️ Bu dosya {line_count} satır. AI'a gönderilirken token tasarrufu için "
                    f"yalnızca baş ve son {core.MAX_CONTEXT_LINES // 2}'şer satır gönderiliyor."
                )
        if st.button("Revizyonu Bitir / Dosyayı Kaldır"):
            st.session_state.selected_file_for_revision = None
            st.session_state.loaded_file_content = ""
            st.session_state.pending_code_to_save = None
            st.session_state.messages.append({"role": "assistant", "content": "Revizyon modu kapatıldı."})
            st.rerun()
    else:
        st.info("Şu an bir dosya revize edilmiyor. `oku <dosya_adı>` veya `revize et <dosya_adı>` komutunu kullanın.")

    st.subheader("Kaydedilen Dosyalar")
    files, error = core.list_generated_files()
    if error:
        st.error(error)
    elif files:
        for f in files:
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.text(f)
            with col2:
                content, _ = core.read_code_from_file(f)
                if content is not None:
                    st.download_button("⬇️", content, file_name=f, key=f"dl_{f}")
    else:
        st.text("Henüz kaydedilmiş dosya bulunmuyor.")

    with st.expander("🗂️ AI'a Giden Proje Bağlamı"):
        st.code(core.get_project_context(), language="text")

    with st.expander("📜 Son Loglar"):
        try:
            with open("agent.log", "r", encoding="utf-8") as f:
                log_lines = f.readlines()[-20:]
            st.code("".join(log_lines) or "Henüz log yok.", language="text")
        except FileNotFoundError:
            st.text("Henüz log dosyası oluşmadı.")

    if st.button("Sohbeti Temizle"):
        st.session_state.messages = []
        st.session_state.selected_file_for_revision = None
        st.session_state.loaded_file_content = ""
        st.session_state.pending_code_to_save = None
        st.rerun()

# --- Agent (session_state'te tutulur, her rerun'da yeniden oluşturulmaz) ---
if st.session_state.agent is None:
    st.session_state.agent = core.CodingAgent(selected_model_name, temperature, max_tokens)
else:
    st.session_state.agent.update_params(selected_model_name, temperature, max_tokens)
agent: core.CodingAgent = st.session_state.agent


def run_agent_command(user_text: str, model_override: Optional[str] = None):
    """
    Bir komutu çalıştırır ve sonucu session_state'e uygular.
    Hem chat_input'tan hem de 'AI Kardeşler' şablon butonlarından çağrılır
    (model_override verilirse, sadece bu çağrı için o modele geçici olarak geçilir).
    """
    if model_override:
        agent.update_params(model_override, temperature, max_tokens)

    st.session_state.messages.append({"role": "user", "content": user_text})
    st.session_state.pending_code_to_save = None

    with st.spinner("Ajan düşünüyor..."):
        result = agent.process_command(
            user_text,
            st.session_state.messages,
            st.session_state.selected_file_for_revision,
            st.session_state.loaded_file_content,
        )

    st.session_state.messages.append({"role": "assistant", "content": result.assistant_message})
    if result.file_state_changed:
        st.session_state.selected_file_for_revision = result.selected_file
        st.session_state.loaded_file_content = result.loaded_content
    st.session_state.pending_code_to_save = result.pending_save
    st.rerun()


# --- AI Kardeşler: Hazır Görev Şablonları ---
TASK_TEMPLATES = [
    {
        "label": "🦙 Llama'ya Sor: Hata Ayıklama",
        "model": "huggingface/meta-llama/Llama-3.3-70B-Instruct",
        "text": "Yukarıdaki kodda syntax hatası var mı? Eğer varsa düzelt ve açıklamalarını ekle.",
    },
    {
        "label": "🐱 Qwen'e Sor: Performans İyileştirme",
        "model": "huggingface/Qwen/Qwen2.5-Coder-32B-Instruct",
        "text": "Bu kodun performansını artırmak için hangi yöntemleri kullanabilirim?",
    },
    {
        "label": "🧠 Claude'a Sor: Mimari ve Kod Kalitesi",
        "model": "anthropic/claude-sonnet-4-6",
        "text": "Bu kodun mimari ve okunabilirlik açısından nasıl geliştirilebilir?",
    },
    {
        "label": "✨ Gemini'ye Sor: Genel Değerlendirme",
        "model": "gemini/gemini-3.5-flash",
        "text": "Bu kodun tüm yönlerini değerlendir ve bütüncül iyileştirmeler öner.",
    },
]

with st.expander("🤝 AI Kardeşler — Hazır Görev Şablonları"):
    if not st.session_state.selected_file_for_revision:
        st.caption(
            "ℹ️ Şu an revizyon modunda bir dosya yok. Önce `oku <dosya_adı>` ile bir dosya "
            "yüklersen, ajan bu şablonları doğrudan o dosya üzerinde çalıştırır."
        )
    for template in TASK_TEMPLATES:
        if st.button(template["label"], key=f"tmpl_{template['model']}", use_container_width=True):
            run_agent_command(template["text"], model_override=template["model"])

# --- Sohbet Geçmişi ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Kullanıcı Girdisi ---
prompt = st.chat_input("Kodlama komutunuzu girin veya bir dosya işlemi yapın...")
if prompt:
    run_agent_command(prompt)

# --- Üretilen Kodu Kaydetme Paneli ---
if st.session_state.get("pending_code_to_save"):
    code_info = st.session_state.pending_code_to_save
    st.subheader("Üretilen Kodu Kaydet")
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        new_filename = st.text_input("Dosya Adı:", value=code_info["filename"], key="save_filename_input")
    with col2:
        if st.button("Kodu Kaydet"):
            if core.is_valid_filename(new_filename):
                save_response = core.save_code_to_file(new_filename, code_info["content"])
                st.session_state.messages.append({"role": "assistant", "content": save_response})
                st.session_state.pending_code_to_save = None
                st.rerun()
            else:
                st.error("Geçersiz dosya adı. Sadece harf, rakam, `_`, `-`, `.` kullanın (örn: app.py).")
    st.code(code_info["content"], language="python")
