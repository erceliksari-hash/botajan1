print('Hello world!')`\n"
        "- `oku my_script.py`\n"
        "- `revize et my_script.py`\n"
        "- `sil my_script.py`\n"
        "- `dosyaları listele`\n\n"
        "_Not: dosya adlarında sadece harf, rakam, `_`, `-`, `.` kullanın (boşluksuz)._"
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

# --- Sohbet Geçmişi ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- Kullanıcı Girdisi ---
prompt = st.chat_input("Kodlama komutunuzu girin veya bir dosya işlemi yapın...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.pending_code_to_save = None

    with st.spinner("Ajan düşünüyor..."):
        result = agent.process_command(
            prompt,
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
    st.code(code_info["content"], language="python") bu kodu incele hatalarini bul ve nasil calistirabilecegimi anlat
