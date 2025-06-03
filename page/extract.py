import streamlit as st
from google import genai
from google.genai import types
from io import BytesIO
from docx import Document  # pip install python-docx

# === 初始化 session_state（注意：不再手动创建 'uploaded_file'） ===
def initialize_states():
    if 'fields' not in st.session_state:
        st.session_state.fields = []
    if 'process_extract' not in st.session_state:
        st.session_state.process_extract = False
    # >>> 去掉下面这行就可以了，否则后面 file_uploader 会报 policy 错误
    # if 'uploaded_file' not in st.session_state:
    #     st.session_state.uploaded_file = None

initialize_states()
st.title('Contract Agent - Document Content Extraction')

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
    key="mode",           # 这里给滑块指定 key="mode"
    on_change=reset_extract
)
selected_model = model_mapping[mode]
desc = mode_description[mode]
st.write(f"Using model: `{selected_model}`, {desc}")

# === 文档上传 ===
st.subheader('Upload a Document (PDF or DOCX)')
uploaded_file = st.file_uploader(
    'Upload one document at a time',
    type=['pdf', 'docx'],
    key='uploaded_file',  # file_uploader 自己在 session_state 里创建 uploaded_file
    on_change=reset_extract
)

# === 新增字段的回调函数 ===
def add_field():
    new_field = st.session_state.get('new_field_input', '').strip()
    if not new_field:
        st.error('Field name cannot be empty')
    elif new_field in st.session_state.fields:
        st.error('Field already exists')
    elif len(st.session_state.fields) >= 20:
        st.error('Maximum number of fields reached: 20')
    else:
        st.session_state.fields.append(new_field)
        st.session_state['new_field_input'] = ''
        reset_extract()    # 统一调用

# === 删除字段的回调函数 ===
def delete_field(idx):
    st.session_state.fields.pop(idx)
    reset_extract()       # 统一调用

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

# === 点击“GO Extract”时设置 process_extract 为 True ===
if uploaded_file and st.session_state.fields:
    st.markdown('---')
    if st.button('GO Extract'):
        st.session_state.process_extract = True

# === 调用 LLM 并展示结果 ===
if st.session_state.process_extract:
    st.markdown('---')
    st.subheader('Extraction Results')

    # 直接用 st.session_state.uploaded_file（由 file_uploader 自己管理）
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

    prompt_lines = [f"**{f}**\n" for f in st.session_state.fields]
    prompt = (
        "Role: You are a professional document content extraction assistant tasked with extracting specified fields from the uploaded document.\n\n"
        + "Please check the uploaded document for the presence of the following fields:\n\n"
        + "".join(prompt_lines)
        + "\nIf present, summarize the corresponding content under each field. If not, write 'NA' under that field.\n\n"
        + "<Example Output>\n\n"
        + "#### Field Name\n"
        + "Field Name Content\n\n"
        + "</Example Output>\n\n"
    )

    client = genai.Client(api_key=st.secrets['GOOGLE_GENAI_API_KEY'])
    with st.spinner("Wait for it...", show_time=True):
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=[doc_part, prompt]
            )
        except Exception as e:
            st.error(f"Network Error: {e} Please email this message to Brian.")
            st.stop()

        if getattr(response, "error", None):
            st.error(f"AI Error: {response.error.message} 1.Try different model. 2.Resources may be insufficient, please email Brian to refuel!")
            st.stop()

    st.success(response.text)
    st.balloons()
