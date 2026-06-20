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
        "show_templates": False,   # AI Kardeşler paneli açık/kapalı
        "detailed_mode": False,    # "Açıklamalı" anahtarı
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

    EXAMPLE_COMMANDS = [
        {"label": "🐍 Fonksiyon Oluştur", "text": "Python'da 'Merhaba Dünya' yazan bir fonksiyon oluştur."},
        {"label": "🧪 Birim Testi Yaz", "text": "Bu dosya için pytest ile birim testleri (unit test) yaz."},
        {"label": "📝 Docstring Ekle", "text": "Bu koddaki tüm fonksiyonlara açıklayıcı docstring ekle."},
        {"label": "🐛 Hata Ayıkla", "text": "Bu kodda hata var mı kontrol et, varsa düzelt ve açıkla."},
        {"label": "💾 Dosyaya Kaydet", "text": "kaydet ornek.py: print('Hello world!')"},
        {"label": "📖 Dosya Oku", "text": "oku ornek.py"},
        {"label": "✏️ Dosyayı Revize Et", "text": "revize et ornek.py"},
        {"label": "🗑️ Dosyayı Sil", "text": "sil ornek.py"},
        {"label": "📋 Dosyaları Listele", "text": "dosyaları listele"},
    ]

    with st.expander("💡 Örnek Komutlar (tıkla, sohbet kutusuna otomatik geçer)", expanded=False):
        st.caption(
            "_Dosya adlarında sadece harf, rakam, `_`, `-`, `.` kullanın (boşluksuz)._"
        )
        ex_cols = st.columns(2)
        for i, ex in enumerate(EXAMPLE_COMMANDS):
            with ex_cols[i % 2]:
                if st.button(ex["label"], key=f"example_cmd_{i}", use_container_width=True):
                    st.session_state["custom_chat_text"] = ex["text"]
        st.caption(
            "💡 Belirli bir modelden görev bazlı yardım istemek için aşağıdaki "
            "**'🤝 AI Kardeşler'** panelindeki hazır şablonları da kullanabilirsin."
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

with st.expander("🤝 AI Kardeşler — Hazır Görev Şablonları", expanded=st.session_state.show_templates):
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

# --- Özel Tasarımlı Sohbet Kutusu ---
# Görseldeki kutuyu (yuvarlak kenarlı, üstte placeholder, altta ikon satırı)
# st.chat_input ile birebir yapamadığımız için st.form + CSS ile elden kuruyoruz.
# "Website" etiketi -> şu an revize edilen dosyanın adı (varsa)
# "+" -> AI Kardeşler panelini aç/kapat
# "Plan" -> "Açıklamalı yanıt" anahtarı (isteğe AI'dan ekstra açıklama ister)
# 🎤 -> şimdilik görsel (gerçek ses kaydı ayrı bir geliştirme gerektirir)
st.markdown(
    """
    <style>
    div[data-testid="stForm"] {
        border: 1px solid #e3e3e3;
        border-radius: 22px;
        padding: 12px 16px 8px 16px;
        background: #fafafa;
    }
    div[data-testid="stForm"] input[type="text"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        font-size: 16px;
    }
    div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button {
        border-radius: 999px;
        border: 1px solid #e3e3e3;
        padding: 4px 10px;
        background: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "show_templates" not in st.session_state:
    st.session_state.show_templates = False
if "detailed_mode" not in st.session_state:
    st.session_state.detailed_mode = False
# (Not: bu ikisi artık init_session_state() içinde en başta ilkleniyor;
#  burada tekrar tutuyoruz sadece güvenlik için - zarar vermez.)

with st.form(key="custom_chat_form", clear_on_submit=True, border=False):
    user_text = st.text_input(
        "Komut",
        placeholder="Kodlama komutunuzu girin veya bir dosya işlemi yapın...",
        label_visibility="collapsed",
        key="custom_chat_text",
    )

    file_tag = st.session_state.selected_file_for_revision
    cols = st.columns([0.07, 0.30, 0.34, 0.13, 0.08, 0.08])

    with cols[0]:
        btn_plus = st.form_submit_button("➕", help="AI Kardeşler şablonlarını göster")
    with cols[1]:
        if file_tag:
            btn_tag = st.form_submit_button(f"📄 {file_tag}  ✕", help="Revizyon dosyasını kaldır")
        else:
            st.caption("Dosya yok")
            btn_tag = False
    with cols[2]:
        st.write("")  # boşluk - görseldeki sağa yaslanma için
    with cols[3]:
        st.session_state.detailed_mode = st.checkbox(
            "Açıklamalı", value=st.session_state.detailed_mode, help="Yanıta ekstra açıklama eklenmesini iste"
        )
    with cols[4]:
        btn_mic = st.form_submit_button("🎤", help="Sesli giriş (yakında)")
    with cols[5]:
        btn_send = st.form_submit_button("↑", type="primary", help="Gönder")

if btn_plus:
    st.session_state.show_templates = not st.session_state.show_templates
    st.rerun()

if btn_tag:
    st.session_state.selected_file_for_revision = None
    st.session_state.loaded_file_content = ""
    st.session_state.pending_code_to_save = None
    st.rerun()

if btn_mic:
    st.toast("🎤 Sesli giriş henüz eklenmedi — yakında!")

if btn_send and user_text.strip():
    final_text = user_text.strip()
    if st.session_state.detailed_mode:
        final_text += " (Lütfen kararlarını da kısaca açıkla.)"
    run_agent_command(final_text)

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
