import streamlit as st
from google import genai
from google.genai import types
from io import BytesIO
from docx import Document  # pip install python-docx
from datetime import datetime

# === 初始化 session_state ===
def initialize_states():
    if 'fields' not in st.session_state:
        st.session_state.fields = []
    if 'process_extract' not in st.session_state:
        st.session_state.process_extract = False
    if 'prev_result' not in st.session_state:
        # 用来保存倒数第二次生成的记录（字典）
        st.session_state.prev_result = None
    if 'last_result' not in st.session_state:
        # 用来保存最新一次生成的记录（字典）
        st.session_state.last_result = None

initialize_states()
st.title('Contract Agent - Document Content Extraction (方案 2)')

# === 统一的“重置 process_extract”函数 ===
def reset_extract():
    st.session_state.process_extract = False

# === Model Selection ===
model_mapping = {
    "Efficiency": "gemma-3-27b-it",
    "Default": "gemini-2.5-flash-preview-05-20",
    "Best Performance": "gemini-2.5-pro-preview-05-06"
}
mode_description = {
    "Efficiency": "Free model, supports up to 32 pages",
    "Default": "Balanced cost and performance model, 1X token cost",
    "Best Performance": "Complex reasoning model, 15X token cost"
}
mode = st.select_slider(
    "Select model performance tier",
    options=list(model_mapping.keys()),
    value="Default",
    key="mode",
    on_change=reset_extract  # 滑动时只重置 process_extract，不清空 prev/last
)
selected_model = model_mapping[mode]
desc = mode_description[mode]
st.write(f"Using model: `{selected_model}`, {desc}")

# === 文档上传 ===
st.subheader('Upload a Document (PDF or DOCX)')
uploaded_file = st.file_uploader(
    'Upload one document at a time',
    type=['pdf', 'docx'],
    key='uploaded_file',
    on_change=reset_extract  # 上传/删除文件时只重置 process_extract，不动 prev/last
)

# === 新增字段的回调函数 ===
def add_field():
    new_field = st.session_state.get('new_field_input', '').strip()
    if not new_field:
        st.error('Field name cannot be empty')
        return
    if new_field in st.session_state.fields:
        st.error('Field already exists')
        return
    if len(st.session_state.fields) >= 20:
        st.error('Maximum number of fields reached: 20')
        return
    st.session_state.fields.append(new_field)
    st.session_state['new_field_input'] = ''
    reset_extract()  # 只把 process_extract 置为 False，不清空 prev/last

# === 删除字段的回调函数 ===
def delete_field(idx):
    st.session_state.fields.pop(idx)
    reset_extract()  # 只把 process_extract 置为 False，不清空 prev/last

# === 添加字段表单 ===
with st.form('add_form', clear_on_submit=True):
    st.subheader('Add Field for Extraction')
    st.text_input('Field Name', key='new_field_input')
    st.form_submit_button('Add', on_click=add_field)

st.markdown('---')

# === 显示当前已选字段 ===
st.subheader('Selected Fields')
if st.session_state.fields:
    for idx, field in enumerate(st.session_state.fields, start=1):
        cols = st.columns([4, 1])
        cols[0].write(f"{idx}. {field}")
        cols[1].button(
            'Delete',
            key=f'delete_{idx}',
            on_click=delete_field,
            args=(idx - 1,)
        )
else:
    st.info('No fields added yet. Please add a field to proceed.')

# === 点击“GO Extract”时：把 process_extract 置 True ===
if uploaded_file and st.session_state.fields:
    st.markdown('---')
    if st.button('GO Extract'):
        st.session_state.process_extract = True

# === 如果 process_extract=True，就调用 LLM；先把 last 推到 prev，再把本次写到 last ===
if st.session_state.process_extract:
    st.markdown('---')
    st.subheader('Running Extraction…')

    # 读取文件内容
    file_bytes = st.session_state.uploaded_file.read()
    file_name = st.session_state.uploaded_file.name.lower()

    if file_name.endswith('.pdf'):
        doc_part = types.Part.from_bytes(
            data=file_bytes,
            mime_type='application/pdf'
        )
    elif file_name.endswith('.docx'):
        doc = Document(BytesIO(file_bytes))
        text = '\n'.join(p.text for p in doc.paragraphs)
        doc_part = text
    else:
        st.error('Only PDF or DOCX formats are supported')
        st.stop()

    # 构建 prompt
    prompt_lines = [f"**{f}**\n" for f in st.session_state.fields]
    prompt = (
        "Role: You are a professional contract administration assistant tasked with extracting specified fields from the uploaded document.\n\n"
        + "Please check the uploaded document for the presence of the following fields:\n\n"
        + "".join(prompt_lines)
        + "\nIf exist, summarize the corresponding content under each field name. If not, write 'NA' under that field.\n\n"
        + "<Example Output>\n\n"
        + "#### Field Name\n"
        + "Field Name Content\n\n"
        + "</Example Output>\n\n"
    )

    # 调用 GenAI
    client = genai.Client(api_key=st.secrets['GOOGLE_GENAI_API_KEY'])
    with st.spinner("Waiting for LLM…", show_time=True):
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=[doc_part, prompt]
            )
        except Exception as e:
            st.error(f"Network Error: {e} Please email this message to Brian.")
            st.stop()

        if getattr(response, "error", None):
            st.error(
                f"AI Error: {response.error.message} "
                "Try: 1.Try different model. 2.Resources may be insufficient, email Brian to refuel!"
            )
            st.stop()

    # 先把当前的 last_result 推到 prev_result
    st.session_state.prev_result = st.session_state.last_result

    # 再把本次的内容写到 last_result
    st.session_state.last_result = {
        "model": selected_model,
        "fields": st.session_state.fields.copy(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "result_text": response.text
    }

    # 提取完成后，把 process_extract 复位
    st.session_state.process_extract = False

# === 渲染 prev_result 与 last_result （仍然用 st.success 输出） ===
if st.session_state.prev_result or st.session_state.last_result:
    st.markdown('---')
    st.subheader('Extraction History (Last 2 Results)')

    # 如果有 prev_result，就先用 st.success 显示它
    if st.session_state.prev_result:
        rec = st.session_state.prev_result
        st.markdown(
            f"**Previous Result**  •  Timestamp: {rec['timestamp']}  •  Model: `{rec['model']}`"
        )
        st.markdown(f"Fields: {rec['fields']}")
        # 这里仍使用 st.success 来展示上一次的纯文本输出
        st.success(rec['result_text'])

    # 再用 st.success 显示最新的一条
    if st.session_state.last_result:
        rec = st.session_state.last_result
        st.markdown(
            f"**Latest Result**  •  Timestamp: {rec['timestamp']}  •  Model: `{rec['model']}`"
        )
        st.markdown(f"Fields: {rec['fields']}")
        st.success(rec['result_text'])
