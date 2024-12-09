import json
from typing import List, Union
import streamlit as st
import os
import yaml
import re
from langchain.callbacks.base import BaseCallbackHandler
from sqlalchemy import inspect, MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateTable

class ToolStreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text
        self.placeholder = self.container.empty()

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.text += token
        self.placeholder.markdown(self.text)
        
    def on_llm_new_result(self, token: str, **kwargs) -> None:
        try:
            parsed_token = json.loads(token)
            formatted_token = json.dumps(parsed_token, indent=2, ensure_ascii=False)
            self.text += "\n\n```json\n" + formatted_token + "\n```\n\n"
        except json.JSONDecodeError:
            if token.strip().upper().startswith("SELECT"):
                self.text += "\n\n```sql\n" + token + "\n```\n\n"
            elif token.strip().upper().startswith("COUNTRY,TOTALREVENUE"):
                self.text += "\n\n```\n" + token + "\n```\n\n"
            else:
                self.text += "\n\n" + token + "\n\n"
        
        self.placeholder.markdown(self.text)

class SQLDatabase:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.metadata = MetaData()

    def get_table_info(self, table_names: List[str]) -> str:
        inspector = inspect(self.engine)
        all_table_names = inspector.get_table_names()

        if not set(table_names).issubset(all_table_names):
            missing_tables = set(table_names) - set(all_table_names)
            raise ValueError(f"table_names {missing_tables} not found in database")

        table_info = []
        for table_name in table_names:
            # Get table DDL
            table = Table(table_name, self.metadata, autoload_with=self.engine)
            create_table = str(CreateTable(table).compile(self.engine))

            # Get sample rows
            sample_rows = self.get_sample_rows(table)

            table_info.append(f"{create_table.rstrip()}\n\n/*\n{sample_rows}\n*/")

        return "\n\n".join(table_info)
    
    def get_sample_rows(self, table: Table) -> str:
        query = select(table).limit(3)
        with self.engine.connect() as conn:
            result = conn.execute(query)
            rows = result.fetchall()

        if not rows:
            return "No rows found"

        column_names = result.keys()
        rows_str = "\n".join([str(dict(zip(column_names, row))) for row in rows])
        return f"3 rows from {table.name} table:\n{rows_str}"
    

    def get_table_schemas(self, table_names: List[str]):
        try:
            tables = [t.strip() for t in table_names]
            data = self.get_table_info(tables)
            if not data:
                print("No data returned from DB")
                return {}

            statements = data.split("\n\n")

            sql_statements = {}
            sample_data = {}
            for statement in statements:
                if "CREATE TABLE" in statement:
                    table_match = statement.split("CREATE TABLE ", 1)[1].split("(", 1)[0].strip()
                    table_name = table_match.strip('`"')
                    sql_statements[table_name] = statement.split("/*")[0].strip()
                if "rows from" in statement:
                    table_name = statement.split("rows from ", 1)[1].split(" table")[0]
                    sample_data[table_name] = statement.split("*/")[0].strip()

            table_details = {}
            for table in tables:
                table_details[table] = {
                    "table": table,
                    "cols": self.get_column_description(table),
                    "create_table_sql": sql_statements.get(table, "Not available"),
                    "sample_data": sample_data.get(table, "No sample data available")
                }

                if not table_details[table]["cols"]:
                    print(f"No columns found for table {table}")

            return table_details
        except Exception as e:
            print(f"Error in get_table_schemas: {str(e)}")
            return {}

    def get_column_description(self, table_name: str):
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        return {col['name']: {'type': str(col['type']), 'nullable': col['nullable']} for col in columns}

    def get_usable_table_names(self):
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def run(self, query: str):
        with self.engine.connect() as conn:
            result = conn.execute(query)
            rows = result.fetchall()

        if not rows:
            return ""

        return [dict(row) for row in rows] 

def stream_converse_messages(client, model, tool_config, messages, system, callback, tokens):
    response = client.converse_stream(
        modelId=model,
        messages=messages,
        system=system,
        toolConfig=tool_config
    )
    
    stop_reason = ""
    message = {"content": []}
    text = ''
    tool_use = {}

    for chunk in response['stream']:
        if 'messageStart' in chunk:
            message['role'] = chunk['messageStart']['role']
        elif 'contentBlockStart' in chunk:
            tool = chunk['contentBlockStart']['start']['toolUse']
            tool_use['toolUseId'] = tool['toolUseId']
            tool_use['name'] = tool['name']
        elif 'contentBlockDelta' in chunk:
            delta = chunk['contentBlockDelta']['delta']
            if 'toolUse' in delta:
                if 'input' not in tool_use:
                    tool_use['input'] = ''
                tool_use['input'] += delta['toolUse']['input']
            elif 'text' in delta:
                text += delta['text']
                callback.on_llm_new_token(delta['text'])
        elif 'contentBlockStop' in chunk:
            if 'input' in tool_use:
                tool_use['input'] = json.loads(tool_use['input'])
                message['content'].append({'toolUse': tool_use})
                tool_use = {}
            else:
                message['content'].append({'text': text})
                text = ''
        elif 'messageStop' in chunk:
            stop_reason = chunk['messageStop']['stopReason']
        elif 'metadata' in chunk:
            tokens['total_input_tokens'] += chunk['metadata']['usage']['inputTokens']
            tokens['total_output_tokens'] += chunk['metadata']['usage']['outputTokens']
    return stop_reason, message


def parse_json_format(json_string):
    json_string = re.sub(r'"""\s*(.*?)\s*"""', r'"\1"', json_string, flags=re.DOTALL)
    json_string = re.sub(r'```json|```|</?response_format>|\n\s*', ' ', json_string)
    json_string = json_string.strip()
    match = re.search(r'({.*})', json_string)
    if match:
        json_string = match.group(1)
    else:
        return "No JSON object found in the string."

    try:
        parsed_json = json.loads(json_string)
    except json.JSONDecodeError as e:
        print("Original output: ", json_string)
        return f"JSON Parsing Error: {e}"
    return parsed_json

def update_tokens_and_costs(tokens):
    st.session_state.tokens['delta_input_tokens'] = tokens['total_input_tokens']
    st.session_state.tokens['delta_output_tokens'] = tokens['total_output_tokens']
    st.session_state.tokens['total_input_tokens'] += tokens['total_input_tokens']
    st.session_state.tokens['total_output_tokens'] += tokens['total_output_tokens']
    st.session_state.tokens['delta_total_tokens'] = tokens['total_tokens']
    st.session_state.tokens['total_tokens'] += tokens['total_tokens']

def calculate_and_display_costs(input_cost, output_cost, total_cost):
    with st.sidebar:
        st.header("Token Usage and Cost")
        st.markdown(f"**Input Tokens:** <span style='color:#555555;'>{st.session_state.tokens['total_input_tokens']}</span> <span style='color:green;'>(+{st.session_state.tokens['delta_input_tokens']})</span> (${input_cost:.2f})", unsafe_allow_html=True)
        st.markdown(f"**Output Tokens:** <span style='color:#555555;'>{st.session_state.tokens['total_output_tokens']}</span> <span style='color:green;'>(+{st.session_state.tokens['delta_output_tokens']})</span> (${output_cost:.2f})", unsafe_allow_html=True)
        st.markdown(f"**Total Tokens:** <span style='color:#555555;'>{st.session_state.tokens['total_tokens']}</span> <span style='color:green;'>(+{st.session_state.tokens['delta_total_tokens']})</span> (${total_cost:.2f})", unsafe_allow_html=True)
    st.sidebar.button("Init Tokens", on_click=init_tokens_and_costs, type="primary")

def init_tokens_and_costs() -> None:
    st.session_state.tokens['delta_input_tokens'] = 0
    st.session_state.tokens['delta_output_tokens'] = 0
    st.session_state.tokens['total_input_tokens'] = 0
    st.session_state.tokens['total_output_tokens'] = 0
    st.session_state.tokens['delta_total_tokens'] = 0
    st.session_state.tokens['total_tokens'] = 0

def load_model_config():
    file_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(file_dir, "config.yml")

    with open(config_file, "r") as file:
        config = yaml.safe_load(file)
    return config['models']

def load_language_config(language):
    file_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(file_dir, "config.yml")

    with open(config_file, "r") as file:
        config = yaml.safe_load(file)
    return config['languages'][language]


def sample_query_indexing(os_client, lang_config):
    rag_query_file = st.text_input(lang_config['rag_query_file'], value="./db_metadata/chinook_example_queries.jsonl")
    if not os.path.exists(rag_query_file):
        st.warning(lang_config['file_not_found'])
        return

    if st.sidebar.button(lang_config['process_file'], key='query_file_process'):
        with st.spinner("Now processing..."):
            os_client.delete_index()
            os_client.create_index() 

            with open(rag_query_file, 'r') as file:
                bulk_data = file.read()

            response = os_client.conn.bulk(body=bulk_data)
            if response["errors"]:
                st.error("Failed")
            else:
                st.success("Success")


def schema_desc_indexing(os_client, lang_config):
    schema_file = st.text_input(lang_config['schema_file'], value="./db_metadata/chinook_detailed_schema.json")
    if not os.path.exists(schema_file):
        st.warning(lang_config['file_not_found'])
        return

    if st.sidebar.button(lang_config['process_file'], key='schema_file_process'):
        with st.spinner("Now processing..."):
            os_client.delete_index()
            os_client.create_index() 

            with open(schema_file, 'r', encoding='utf-8') as file:
                schema_data = json.load(file)

            bulk_data = []
            for table in schema_data:
                for table_name, table_info in table.items():
                    table_doc = {
                        "table_name": table_name,
                        "table_desc": table_info["table_desc"],
                        "columns": [{"col_name": col["col"], "col_desc": col["col_desc"]} for col in table_info["cols"]],
                        "table_summary": table_info["table_summary"],
                        "table_summary_v": table_info["table_summary_v"]
                    }
                    bulk_data.append({"index": {"_index": os_client.index_name, "_id": table_name}})
                    bulk_data.append(table_doc)
            
            bulk_data_str = '\n'.join(json.dumps(item) for item in bulk_data) + '\n'

            response = os_client.conn.bulk(body=bulk_data_str)
            if response["errors"]:
                st.error("Failed")
            else:
                st.success("Success")

