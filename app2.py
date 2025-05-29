import streamlit as st
from google import genai
from google.genai import types
from io import BytesIO
from docx import Document  # pip install python-docx

# Initialize the list of fields
def initialize_states():
    if 'fields' not in st.session_state:
        st.session_state.fields = []
    if 'process_extract' not in st.session_state:
        st.session_state.process_extract = False

initialize_states()

st.title('Document Field Template Designer and Content Extractor')

# === Retrieve API Key from Streamlit secrets ===
try:
    api_key = st.secrets['GOOGLE_GENAI_API_KEY']
except KeyError:
    st.error('API key not found. Please add GOOGLE_GENAI_API_KEY to .streamlit/secrets.toml or the Streamlit Cloud secrets.')
    st.stop()

# === Model Selection ===
model_mapping = {
    "Fast": "gemma-3-27b-it",
    "Balanced": "gemini-2.5-flash-preview-05-20",
    "Best Performance": "gemini-2.5-pro-preview-05-06"
}
mode_description = {
    "Fast": "High speed, supports up to 32 pages, zero token cost",
    "Balanced": "Balanced performance and cost, 1× token cost",
    "Best Performance": "For complex tasks, 15× token cost"
}
mode = st.select_slider(
    "Select model performance tier",
    options=list(model_mapping.keys()),
    value="Fast"
)
selected_model = model_mapping[mode]
desc = mode_description[mode]
st.write(f"Current tier: {mode}")
st.write(f"Using model: `{selected_model}`, {desc}")

# === Document Upload ===
st.subheader('Upload a Document (PDF or DOCX)')
uploaded_file = st.file_uploader('Upload one document at a time', type=['pdf', 'docx'])

# === Callback to add a new field ===
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
        st.session_state.process_extract = False

# === Form to add a new field template ===
with st.form('add_form', clear_on_submit=True):
    st.subheader('Add Field for Extraction')
    st.text_input('Field Name', key='new_field_input')
    st.form_submit_button('Add', on_click=add_field)

st.markdown('---')

# === Display current field templates ===
st.subheader('Current Field Templates')
if st.session_state.fields:
    for idx, field in enumerate(st.session_state.fields, start=1):
        cols = st.columns([4, 1])
        cols[0].write(f"{idx}. {field}")
        cols[1].button(
            'Delete',
            key=f'delete_{idx}',
            on_click=lambda i=idx-1: st.session_state.fields.pop(i)
        )
else:
    st.info('No fields added yet. Please add a field to proceed.')

# === Confirmation button to start extraction ===
if uploaded_file and st.session_state.fields:
    st.markdown('---')
    if st.button('Confirm and Extract'):
        st.session_state.process_extract = True

# === Extract and display results ===
if st.session_state.process_extract:
    st.markdown('---')
    st.subheader('Extraction Results')

    file_bytes = uploaded_file.read()
    file_name = uploaded_file.name.lower()

    # 1️⃣ Prepare document content
    if file_name.endswith('.pdf'):
        # Use PDF bytes directly
        doc_part = types.Part.from_bytes(
            data=file_bytes,
            mime_type='application/pdf'
        )
    elif file_name.endswith('.docx'):
        # Extract text from DOCX
        doc = Document(BytesIO(file_bytes))
        text = '\n'.join(p.text for p in doc.paragraphs)
        doc_part = text  # Provide text directly to the model
    else:
        st.error('Only PDF or DOCX formats are supported')
        st.stop()

    # 2️⃣ Build the prompt for the model
    prompt_lines = [f"**{f}**\n" for f in st.session_state.fields]
    prompt = (
        "Role: You are a professional document content extraction assistant tasked with extracting specified fields from the uploaded document.\n\n"
        + "Please check the uploaded document for the presence of the following fields:\n\n"
        + "".join(prompt_lines)
        + "\nIf present, summarize the corresponding content under each field. Do not generate a table."
        + "\n\n<Example Output>\n\n"
        + "#### Field Name\n"
        + "Field Name Content\n\n"
        + "</Example Output>\n\n"
        + "Note: If a field is not found in the document, write 'NA' under that field.\n"
    )

    # 3️⃣ Call the GenAI model
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=selected_model,
        contents=[doc_part, prompt]  # Document content first, then prompt
    )

    # Display the model output
    st.divider()
    st.success(response.text)
    st.balloons()
