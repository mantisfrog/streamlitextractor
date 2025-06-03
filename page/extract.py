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
    if 'history' not in st.session_state:
        # history: 列表，每个元素结构为 {"model":..., "fields":[...], "timestamp":..., "result_text":...}
        st.session_state.history = []

initialize_states()
st.title('Contract Agent - Document Content Extraction (方案 1)')

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
    key="mode",           # 滑块的键
    on_change=reset_extract  # 滑动时只重置 process_extract，不影响 history
)
selected_model = model_mapping[mode]
desc = mode_description[mode]
st.write(f"Using model: `{selected_model}`, {desc}")

# === 文档上传 ===
st.subheader('Upload a Document (PDF or DOCX)')
uploaded_file = st.file_uploader(
    'Upload one document at a time',
    type=['pdf', 'docx'],
    key='uploaded_file',    # file_uploader 自行创建这个键
    on_change=reset_extract # 上传/删除文件时只重置 process_extract，不动 history
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
    reset_extract()  # 只把 process_extract 置 False，不清空 history

# === 删除字段的回调函数 ===
def delete_field(idx):
    st.session_state.fields.pop(idx)
    reset_extract()  # 只把 process_extract 置 False，不清空 history

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

# === 点击“GO Extract”时：把 process_extract 置 True（不清空 history） ===
if uploaded_file and st.session_state.fields:
    st.markdown('---')
    if st.button('GO Extract'):
        # 只把 process_extract 置 True，实际调用放到下面
        st.session_state.process_extract = True

# === 如果 process_extract=True，就调用 LLM 并把结果 push 到 history；然后清除标志 ===
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

    # 构建本次的记录
    new_record = {
        "model": selected_model,
        "fields": st.session_state.fields.copy(),  # 深拷贝当时的字段列表
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "result_text": response.text
    }
    # 将新记录 append 到 history
    st.session_state.history.append(new_record)
    # 如果长度超过 2，就弹出最早的一条
    if len(st.session_state.history) > 2:
        st.session_state.history.pop(0)

    # 提取完成，把 process_extract 复位
    st.session_state.process_extract = False

# === 展示 history 中最多 2 条结果 ===
if st.session_state.history:
    st.markdown('---')
    st.subheader('Extraction History (Last 2 Results)')

    # 如果有倒数第二条，就先展示它
    if len(st.session_state.history) == 2:
        rec = st.session_state.history[0]
        st.markdown(f"**Previous Result**  •  Timestamp: {rec['timestamp']}  •  Model: `{rec['model']}`")
        st.markdown(f"Fields: {rec['fields']}")
        st.text_area("Result ①", rec['result_text'], height=200)

    # 再展示最新的一条
    latest = st.session_state.history[-1]
    st.markdown(f"**Latest Result**  •  Timestamp: {latest['timestamp']}  •  Model: `{latest['model']}`")
    st.markdown(f"Fields: {latest['fields']}")
    st.text_area("Result ②", latest['result_text'], height=200)
