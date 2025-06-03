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
    if 'output_format' not in st.session_state:
        # “Paragraph” 或 “Bullet Points”
        st.session_state.output_format = "Paragraph"
    if 'word_count' not in st.session_state:
        # 每个字段摘要的最大词数
        st.session_state.word_count = 30

initialize_states()
st.title('Contract Agent - Document Content Extraction')

# === 统一的“重置 process_extract”函数（不清空 prev/last） ===
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
    on_change=reset_extract,  # 滑块移动时只重置 process_extract，不动 prev/last
    label_visibility="hidden"
)
selected_model = model_mapping[mode]
desc = mode_description[mode]
st.write(f"`{selected_model}`, {desc}")

# === 文档上传 ===
st.subheader('Upload a Document (PDF or DOCX)')
uploaded_file = st.file_uploader(
    'Upload one document at a time',
    type=['pdf', 'docx'],
    key='uploaded_file',
    on_change=reset_extract
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
    st.subheader('Add Field Name')
    st.text_input('Build your template', key='new_field_input')
    st.form_submit_button('Add', on_click=add_field)

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

# === Output Style 区块 ===
st.subheader('Output Style')

# 1. 让用户选择 Paragraph 或 Bullet Points，加 on_change
st.radio(
    label="Choose summary style:",
    options=["Paragraph", "Bullet Points"],
    index=0,                # 默认 Paragraph
    key="output_format",
    on_change=reset_extract
)

# 2. 全局 word count 上限（每个字段摘要的最大词数），也加 on_change
st.number_input(
    label="Summary Word Count (max words per field)",
    min_value=0,
    max_value=1000,
    step=5,
    key="word_count",
    on_change=reset_extract
)

# === 点击“GO Extract”时：把 process_extract 置 True ===
if uploaded_file and st.session_state.fields:
    if st.button('GO Extract'):
        st.session_state.process_extract = True

# === 如果 process_extract=True，就调用 LLM；
#     先把 last 推到 prev，再把本次写到 last ===
if st.session_state.process_extract:
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

    # 构建 prompt 时，调用以下 session_state 值：
    # - st.session_state["output_format"]  # "Paragraph" or "Bullet Points"
    # - st.session_state["word_count"]     # 最大词数
    # 以及 fields、selected_model 等常规信息
    prompt_lines = [f"**{f}**  \n" for f in st.session_state.fields]
    prompt = f"""
    Role: You are a professional contract administration assistant tasked with extracting specified fields from the uploaded document.
    Please check the uploaded document for the presence of the following 'Field Names':  \n
    {''.join(prompt_lines)}
    If present, summarize the corresponding content under each field name according to the chosen output style. If not, write 'NA' under that field.  \n
    <Output Format>  \n   
    Summary Format: {st.session_state.output_format}  \n
    Word Count of Each 'Field Name Summary': {st.session_state.word_count} words.  \n
    </Output Format>  \n
    <Example Output>  \n
    #### Field Name  \n
    Field Name Summary  \n
    </Example Output>
    """
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
        "output_style": st.session_state.output_format,
        "word_count": st.session_state.word_count,
        "result_text": response.text
    }

    # 提取完成后，把 process_extract 复位
    st.session_state.process_extract = False

# === 渲染结果：先展示 last_result（最新一次），再展示 prev_result（上一次），使用 st.success 输出 ===
if st.session_state.last_result or st.session_state.prev_result:
    st.subheader('Extraction Results')

    # 先显示“最新一次”
    if st.session_state.last_result:
        rec = st.session_state.last_result
        st.markdown(
            f"**Latest Result**  \n(Model: `{rec['model']}`  •  "
            f"Style: {rec['output_style']}  •  Max Words: {rec['word_count']})"
        )
        st.success(rec['result_text'])

    # 再显示“上一次”
    if st.session_state.prev_result:
        rec = st.session_state.prev_result
        st.markdown(
            f"**Previous Result**  \n(Model: `{rec['model']}`  •  "
            f"Style: {rec['output_style']}  •  Max Words: {rec['word_count']})"
        )
        st.success(rec['result_text'])
