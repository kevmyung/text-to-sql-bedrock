import streamlit as st
import os
from typing import Dict, Tuple, List, Union
from src.db_utils import DB_Tool_Client
from src.insight_utils import analyze_main
from src.common_utils import load_model_config, load_language_config, display_chat_messages, update_tokens_and_costs, calculate_and_display_costs, ToolStreamHandler
from src.models import ChatModel, calculate_cost_from_tokens
from src.opensearch import init_opensearch


st.set_page_config(page_title='Bedrock AI Chatbot', page_icon="🤖", layout="wide")
st.title("🤖 Bedrock AI Chatbot")

lang_config = {}
INIT_MESSAGE = {"role": "assistant", "content": ""}

def set_init_message(init_message: str) -> None:
    INIT_MESSAGE["content"] = init_message

def handle_language_change() -> None:
    global lang_config
    lang_config = load_language_config(st.session_state['language_select'])
    set_init_message(lang_config['init_message'])
    new_chat()

def new_chat() -> None:
    st.session_state["messages"] = [INIT_MESSAGE]

def parse_conversation_history(messages):
    history = ""
    for message in messages:
        role = message.get('role', 'unknown')
        content = message.get('content', '')
        if isinstance(content, list):
            content = ' '.join([item.get('text', '') for item in content])
        history += f"{role}: {content}\n"
    return history

def database_setting():
    database_selection = st.sidebar.selectbox(
        lang_config['database'],
        ('Sample', 'MySQL', 'PostgreSQL', 'Redshift', 'SQLite', 'Presto', 'Oracle')
    )

    if database_selection == "Sample":
        database_dialect = "SQLite"
        database_uri = "sqlite:///Chinook.db"
    else:
        database_dialect = database_selection
        database_uri = st.sidebar.text_input("Database URI", value="", placeholder="dbtype://user:pass@hostname:port/dbname")
        if not database_uri:
            st.info(lang_config['database_uri'])
            st.stop()

    database_config = {
        "dialect": database_dialect,
        "uri": database_uri
    }  
    return database_config

def render_sidebar() -> Tuple[Dict, Dict, Dict]:
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.button("New Chat", on_click=new_chat, type="primary")
    with col2:
        if st.button("Analyze", type="primary"):
            st.session_state.page = "analyze"
            st.rerun()
    global lang_config
    language = st.sidebar.selectbox(
        'Language 🌎',
        ['Korean', 'English'],
        key='language_select',
        on_change=handle_language_change
    )
    lang_config = load_language_config(language)
    set_init_message(lang_config['init_message'])

    model_config = load_model_config()
    model_name_select = st.sidebar.selectbox(
        lang_config['model_selection'],
        list(model_config.keys()),
        key='model_name',
    )
    model_info = model_config[model_name_select]

    model_info["region_name"] = st.sidebar.selectbox(
        lang_config['region'],
        ['us-west-2', 'us-east-1', 'ap-northeast-1'],
        key='bedrock_region',
    )

    model_kwargs = {
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": 200,
        "max_tokens": 20480
    }

    database_config = database_setting()

    return model_info, model_kwargs, database_config

def main() -> None:
    model_info, model_kwargs, database_config = render_sidebar()
    chat_model = ChatModel(model_info, model_kwargs)
    sql_os_client, schema_os_client = init_opensearch(chat_model.emb, lang_config)

    if "messages" not in st.session_state:
        st.session_state.messages = [INIT_MESSAGE]
    if "tokens" not in st.session_state:
        st.session_state.tokens = {'total_input_tokens': 0, 'total_output_tokens': 0, 'total_tokens': 0, 'delta_input_tokens': 0, 'delta_output_tokens': 0, 'delta_total_tokens': 0}

    display_chat_messages([])
    prompt = st.chat_input(placeholder=lang_config['example_msg'])

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)
        
        assistant_placeholder = st.empty()
        with assistant_placeholder.container():
            with st.chat_message("assistant"):
                history = parse_conversation_history(st.session_state.messages[1:][-3:])
                db_client = DB_Tool_Client(model_info, database_config, st.session_state['language_select'], sql_os_client, schema_os_client, prompt, history)
                with st.expander("Scratchpad (Click to expand)", expanded=True): 
                    response_placeholder = st.empty()  
                    callback = ToolStreamHandler(response_placeholder)
                    response, tokens = db_client.invoke(callback)
                update_tokens_and_costs(tokens)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.markdown(response)                
    
    input_cost, output_cost, total_cost = calculate_cost_from_tokens(st.session_state.tokens, model_info['model_id'])
    calculate_and_display_costs(input_cost, output_cost, total_cost)


if __name__ == "__main__":
    if 'page' not in st.session_state:
        st.session_state.page = "main"
    
    if st.session_state.page == "main":
        main()
    if st.session_state.page == "analyze":
        analyze_main()

