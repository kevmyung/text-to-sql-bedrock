from typing import Dict, Tuple, List, Union
import streamlit as st
import pandas as pd
import boto3
import os
import io
import re
import json
from io import StringIO
import mimetypes
import plotly.express as px
from botocore.config import Config
from .common_utils import load_model_config, load_language_config
from .prompts import get_data_filtering_prompt, get_code_generation_prompt
from .common_utils import process_uploaded_files, CustomUploadedFile

INIT_MESSAGE = {"role": "assistant", "content": ""}
lang_config = {}

def set_init_message(init_message: str) -> None:
    INIT_MESSAGE["content"] = init_message

class Insight_Tools:
    def __init__(self, model_info, language, dataframe):
        self.model = model_info['model_id']
        self.region = model_info['region_name']
        self.language = language
        self.top_k = 5
        self.boto3_client = self.init_boto3_client(self.region)
        self.sampling_method = 'uniform'
        self.dataframe = dataframe

    def init_boto3_client(self, region: str):
        retry_config = Config(
            region_name=region,
            retries={"max_attempts": 10, "mode": "standard"}
        )
        return boto3.client("bedrock-runtime", region_name=region, config=retry_config)
    
    def preprocessing_dataframe(self):
        rows, cols = self.dataframe.shape
        if rows * cols > 200:
            #data = self.sampling_data(self.dataframe, rows, cols)
            self.datatype = "sampled_"
        else:
            self.datatype = "full_"

    def formatting_code_frame(self, csv_string_escaped, code_block):
        imports = "import pandas as pd\nimport plotly.express as px\n\n"
        dataframe_code = f'dataframe = pd.read_csv(io.StringIO("{csv_string_escaped}"))\n\n'
        plot_code = "\n\nst.plotly_chart(fig)"
        full_code_block = imports + dataframe_code + code_block + plot_code
        return full_code_block

    def code_generation(self, plot_type):
        csv_string = self.dataframe.to_csv(index=False)
        csv_string_escaped = csv_string.replace('\n', '\\n').replace('"', '\\"')
        self.preprocessing_dataframe()
        
        sys_prompt, usr_prompt = get_code_generation_prompt(csv_string_escaped, self.datatype, plot_type)
        response = self.boto3_client.converse(modelId=self.model, messages=usr_prompt, system=sys_prompt)
        code_block = response['output']['message']['content'][0]['text']
        full_code_block = self.formatting_code_frame(csv_string_escaped, code_block)
        return full_code_block

    def get_unique_column_values(self):
        unique_values = {col: self.dataframe[col].unique().tolist() for col in self.dataframe}
        
    def sampling_data(self, data, rows, cols):
        # filtering method selection
        sys_prompt, usr_prompt = get_data_filtering_prompt(self.prompt, data.head().to_string(), data.tail().to_string(), rows-10)
        response = self.client.converse(
            modelId=self.model,
            messages=usr_prompt,
            system=sys_prompt
        )
        parsed_json = self.parse_json_format(response['output']['message']['content'][0]['text'])
        sampling_method = parsed_json['sampling_method']

        if sampling_method == 'uniform':
            step = rows * cols // 200
            sampled_data = data.iloc[::step, :]
        
        elif sampling_method == 'random':
            sampled_data = data.sample(n=200 // cols, random_state=42)
        
        elif sampling_method == 'time_based':
            data['Date'] = pd.to_datetime(data['Date'])
            sampled_data = data.set_index('Date').resample('1D').first().dropna().reset_index()
        
        elif sampling_method == 'sliding_window':
            window_size = rows // (200 // cols)
            sampled_data = data.rolling(window=window_size).mean().dropna().iloc[::window_size, :]

        return sampled_data


class Insight_Tool_Client:
    def __init__(self, model_info, language, dataframe, plot_type):
        self.model = model_info['model_id']
        self.region = model_info['region_name']
        self.language = language
        self.top_k = 5
        #self.tool_config = self.load_tool_config()
        self.boto3_client = self.init_boto3_client(self.region)
        self.tokens = {'total_input_tokens': 0, 'total_output_tokens': 0, 'total_tokens': 0}
        self.plot_type = plot_type
        self.insight_tools = Insight_Tools(model_info, language, dataframe)

    def init_boto3_client(self, region: str):
        retry_config = Config(
            region_name=region,
            retries={"max_attempts": 10, "mode": "standard"}
        )
        return boto3.client("bedrock-runtime", region_name=region, config=retry_config)
    
    def invoke(self):
        code = self.insight_tools.code_generation(self.plot_type)
        try:
            exec(code)
        except:
            st.write("An error occurred. Please try again.")
        
        return code

def handle_language_change() -> None:
    global lang_config
    lang_config = load_language_config(st.session_state['language_select_insight'])
    set_init_message(lang_config['init_message'])

def render_sidebar() -> Tuple[Dict, Dict, Dict]:
    if st.sidebar.button("Back to Main", type="primary"):
        st.session_state.page = "main"
        st.session_state.file_content = []
        st.rerun()
    global lang_config
    language = st.sidebar.selectbox(
        'Language 🌎',
        ['Korean', 'English'],
        key='language_select_insight',
        on_change=handle_language_change
    )
    lang_config = load_language_config(language)
    set_init_message(lang_config['init_message'])

    model_config = load_model_config()
    model_name_select = st.sidebar.selectbox(
        lang_config['model_selection'],
        list(model_config.keys()),
        key='model_name_insight',
    )
    model_info = model_config[model_name_select]

    model_info["region_name"] = st.sidebar.selectbox(
        lang_config['region'],
        ['us-west-2', 'us-east-1', 'ap-northeast-1'],
        key='bedrock_region_insight',
    )
    
    return model_info

def input_file_processor():
    if 'file_content' not in st.session_state:
        st.session_state.file_content = []
    uploaded_files = []
    
    file_path = st.sidebar.text_input('File Path (CSV, JPG, PNG)', value="./result_files/sample_data.csv")
    file_path_button = st.sidebar.button('Process File')

    uploaded_file = st.sidebar.file_uploader('File Uploader', type=["jpg", "jpeg", "png", "csv"], key="image_uploader_key")
    if file_path_button:
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                file_data = io.BytesIO(f.read())
            file_type, _ = mimetypes.guess_type(file_path)
            custom_file = CustomUploadedFile(name=os.path.basename(file_path), type=file_type, data=file_data)
            uploaded_files.append(custom_file)
        else:
            st.sidebar.error('File does not exist.')
    elif uploaded_file:
        custom_file = CustomUploadedFile(name=uploaded_file.name, type=uploaded_file.type, data=io.BytesIO(uploaded_file.getvalue()))
        uploaded_files.append(custom_file)

    if uploaded_files:
        st.session_state.file_content = process_uploaded_files(uploaded_files, [], [])
    
    return st.session_state.file_content

def select_plot_type(container):
    plot_types = ["Auto", "Bar Chart", "Line Chart", "Area Chart", "Box Plot", "Scatter Plot", "Bubble Chart"]   
    plot_type = container.selectbox("Choose Plot Type", options=plot_types, index=0)
    return plot_type

def analyze_main():    
    model_info = render_sidebar()
    input_file_processor()
    if 'file_content' in st.session_state and st.session_state.file_content:
        if st.session_state.file_content[0]['type'] == 'text':
            input_dataframe = pd.read_csv(StringIO(st.session_state.file_content[0]['text']))
            plot_type_container = st.empty()
            plot_type = select_plot_type(plot_type_container)
            insight_client = Insight_Tool_Client(model_info, st.session_state['language_select_insight'], input_dataframe, plot_type)
            with st.spinner(f"Generating a visualization"):
                insight_client.invoke()
        if st.session_state.file_content[0]['type'] == 'image':
            print("image_analyzer")
        else:
            print("Unknown type")
        