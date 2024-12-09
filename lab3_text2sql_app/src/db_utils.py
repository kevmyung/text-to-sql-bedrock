from botocore.config import Config
import boto3
import pandas as pd
import uuid
import pytz
import json
import logging
import os
import re
import streamlit as st
import warnings
from datetime import datetime
from sqlalchemy import create_engine
from typing import List, Dict, Any, Union

from sqlalchemy import inspect, MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateTable
from sqlalchemy import exc as sa_exc

from .common_utils import parse_json_format, stream_converse_messages
from .opensearch import OpenSearchVectorRetriever, OpenSearchClient
from .prompts import (
    get_table_selection_prompt, 
    get_query_generation_prompt, 
    get_prompt_refinement_prompt, 
    get_query_validation_prompt,
    get_answer_generation_prompt,
    get_global_prompt
)

warnings.filterwarnings('ignore', category=sa_exc.SAWarning)

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
    

    def get_table_schemas(self, table_names: List[str]) -> Dict[str, Dict]:
        try:
            tables = [t.strip() for t in table_names]
            data = self.get_table_info(tables)
            if not data:
                logging.warning("No data returned from DB")
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
            logging.error(f"Error in get_table_schemas: {str(e)}")
            return {}

    def get_column_description(self, table_name: str) -> Dict[str, Dict]:
        inspector = inspect(self.engine)
        columns = inspector.get_columns(table_name)
        return {col['name']: {'type': str(col['type']), 'nullable': col['nullable']} for col in columns}

    def get_usable_table_names(self):
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def run(self, query: str) -> Union[str, List[Dict[str, Any]]]:
        with self.engine.connect() as conn:
            result = conn.execute(query)
            rows = result.fetchall()

        if not rows:
            return ""

        return [dict(row) for row in rows]


class DB_Tools:
    def __init__(self, tokens: dict, uri: str, dialect: str, model: str, region: str, sql_os_client: OpenSearchClient, schema_os_client: OpenSearchClient, language: str, prompt: str, history: str):
        self.tokens = tokens
        self.uri = uri
        self.dialect = dialect
        self.model = model
        self.region = region
        self.language = language
        self.sql_os_client = sql_os_client
        self.schema_os_client = schema_os_client
        self.boto3_client = self.init_boto3_client(region)
        self.engine = create_engine(uri)
        self.db = SQLDatabase(self.engine)
        #self.prompt = self.prompt_refinement(prompt, history)
        self.prompt = prompt
        self.init_tool_state(prompt)
        self.samples = self.collect_samples()
        self.display_samples()
        self.retry = 0

    def init_boto3_client(self, region: str):
        retry_config = Config(
            region_name=region,
            retries={"max_attempts": 10, "mode": "standard"}
        )
        return boto3.client("bedrock-runtime", region_name=region, config=retry_config)

    def init_tool_state(self, prompt):
        self.tool_state = {
            "user_prompt": prompt,
            "refined_prompt": self.prompt,
            "initial_query": "None",
            "final_query": "None",
            "sql_query_file": "None",
            "result_csv_file": "None",
            "failure_log": "None",
            "failed_query": "None",
            "search_result": "None",
            "success": "False"
        }

    def update_tokens(self, res):
        self.tokens["total_input_tokens"] += res["usage"]["inputTokens"]
        self.tokens["total_output_tokens"] += res["usage"]["outputTokens"]

    def collect_samples(self):
        with st.spinner("Collecting Sample Queries..."):
            return self.get_sample_queries()

    def display_samples(self):
        with st.expander("Referenced Sample Queries (Click to expand)", expanded=False):
            self.print_sql_samples(self.samples)

    def print_sql_samples(self, selected_samples: List[str]) -> None:
        if not selected_samples:
            st.text("There is no similar samples.")
            return
        
        for sample in selected_samples:
            try:
                input_text = sample.get('input', 'No input available')
                query = sample.get('query', 'No query available')

                st.markdown(f"**Input:** {input_text}")
                st.markdown(f"**Query:**")
                st.code(query, language='sql')
                st.markdown('<div style="margin: 5px 0;"><hr style="border: none; border-top: 1px solid #ccc; margin: 0;" /></div>', unsafe_allow_html=True)
            except Exception as e:
                st.text(f"Error processing sample: {str(e)}") 
 
    def get_sample_queries(self): 
        sql_os_retriever = OpenSearchVectorRetriever(
            self.sql_os_client, 
            self.region, 
            k=10
        )
        samples = sql_os_retriever.vector_search(self.prompt, self.sql_os_client.index_name)
        page_contents = [json.loads(doc.page_content) for doc in samples]

        bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=self.region)
        rerank_model_id = "cohere.rerank-v3-5:0"
        model_package_arn = f"arn:aws:bedrock:{self.region}::foundation-model/{rerank_model_id}"

        text_sources = [
            {
                "type": "INLINE",
                "inlineDocumentSource": {
                    "type": "TEXT",
                    "textDocument": {
                        "text": content['input'],
                    }
                }
            } for content in page_contents
        ]

        response = bedrock_agent_runtime.rerank(
                    queries=[
                        {
                            "type": "TEXT",
                            "textQuery": {
                                "text": self.prompt
                            }
                        }
                    ],
                    sources=text_sources,
                    rerankingConfiguration={
                        "type": "BEDROCK_RERANKING_MODEL",
                        "bedrockRerankingConfiguration": {
                            "numberOfResults": 3,
                            "modelConfiguration": {
                                "modelArn": model_package_arn,
                            }
                        }
                    }
                )
        
        reranked_samples = []
        for result in response['results']:
            index = result['index']
            sample_input = page_contents[index]['input']
            sample_query = page_contents[index]['query']
            reranked_samples.append({
                'input': sample_input,
                'query': sample_query,
            })

        return reranked_samples


    def get_table_summaries_by_similarities(self):
        schema_os_retriever = OpenSearchVectorRetriever(
            self.schema_os_client, 
            self.region, 
            k=5
        )
        matched_tables = schema_os_retriever.vector_search(self.prompt, self.schema_os_client.index_name)

        serializable_tables = []
        for document in matched_tables:
            table_data = json.loads(document.page_content)
            serializable_tables.append(table_data)

        return json.dumps(serializable_tables, ensure_ascii=False)

    def get_table_summaries_all(self):
        schema_os_retriever = OpenSearchVectorRetriever(
            self.schema_os_client, 
            self.region
        )
        documents = schema_os_retriever.get_all_documents(self.schema_os_client.index_name)

        table_descriptions = {}
        for doc in documents:
            content = json.loads(doc.page_content)
            table_name = content['table_name']
            table_desc = content['table_summary']
            table_descriptions[table_name] = table_desc

        return table_descriptions

    def get_column_description(self, table_name: str) -> Dict[str, str]:
        query = {
            "_source": ["columns.col_name", "columns.col_desc"],
            "query": {
                "match": {
                    "table_name": table_name
                }
            }
        }
        response = self.schema_os_client.conn.search(index=self.schema_os_client.index_name, body=query)
        if response['hits']['total']['value'] > 0:
            source = response['hits']['hits'][0]['_source']
            columns = source.get('columns', [])
            if columns:
                return {col['col_name']: col['col_desc'] for col in columns}
            else:
                return {}
        else:
            return {}

    def get_table_schemas(self, table_names: List[str]) -> Dict[str, Dict]:
        try:
            tables = [t.strip() for t in table_names]
            sql_statements = {}
            sample_data = {}
            data = self.db.get_table_info(tables)
            if not data:
                logging.warning("No data returned from DB")
                return {}

            statements = data.split("\n\n")

            for statement in statements:
                if "CREATE TABLE" in statement:
                    table_match = re.search(r"CREATE TABLE (?:`|\")?(\w+)(?:`|\")?", statement)
                    if table_match:
                        table_name = table_match.group(1)
                        sql_statements[table_name] = statement.split("/*")[0].strip()
                elif "rows from" in statement:
                    table_name_match = re.search(r"rows from (\w+) table", statement)
                    if table_name_match:
                        table_name = table_name_match.group(1)
                        sample_data[table_name] = statement.strip()

            table_details = {}
            for table in tables:
                table_desc = self.get_column_description(table)
                table_details[table] = {
                    "table": table,
                    "cols": table_desc if table_desc else {},
                    "create_table_sql": sql_statements.get(table, "Not available"),
                    "sample_data": sample_data.get(table, "No sample data available")
                }

                if not table_details[table]["cols"]:
                    print(f"No columns found for table {table}")
            return table_details
        except Exception as e:
            logging.error(f"Error in get_table_schemas: {str(e)}")
            return {}
    
    def get_explain_query(self, original_query):
        explain_statements = {
            'mysql': "EXPLAIN {query}",
            'mariadb': "EXPLAIN {query}",
            'sqlite': "EXPLAIN QUERY PLAN {query}",
            'oracle': "EXPLAIN PLAN FOR\n{query}\n\nSELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);",
            'postgresql': "EXPLAIN ANALYZE {query}",
            'postgres': "EXPLAIN ANALYZE {query}",
            'redshift': "EXPLAIN ANALYZE {query}",
            'presto': "EXPLAIN ANALYZE {query}",
            'sqlserver': "SET STATISTICS PROFILE ON; {query} SET STATISTICS PROFILE OFF;",
            'bigquery': "BigQuery requires using the API to get query explanation."
        }
        return explain_statements.get(self.dialect.lower(), f"Unsupported dialect: {self.dialect}. Please provide the EXPLAIN syntax manually.").format(query=original_query)

    def save_to_csv(self, data, query: str):
        try:
            if isinstance(data, str):
                data = eval(data) 

            if not data:
                return {"failure_log": "No data to save."}

            df = pd.DataFrame(data)
            df = df.where(pd.notnull(df), None)

            current_time = datetime.now().strftime("%Y%m%d%H%M%S")
            random_id = str(uuid.uuid4())
            folder_path = "./result_files"
            os.makedirs(folder_path, exist_ok=True)

            csv_file = f"{folder_path}/query_result_{current_time}_{random_id}.csv"
            query_file = f"{folder_path}/query_{current_time}_{random_id}.sql"

            df.to_csv(csv_file, index=False)
            with open(query_file, 'w') as file:
                file.write(query)

            return csv_file, query_file, df

        except Exception as e:
            logging.error(f"Error in save_to_csv: {str(e)}")
            return {"failure_log": f"An error occurred while saving the data: {str(e)}"}

    def query_failure_handling(self, log, query):
        self.tool_state["failure_log"] = log
        self.tool_state["failed_query"] = query
        if self.retry >= 2:
            action = "Stop the sequence."
        elif "no such" in log:
            action = "Use the schema_exploration tool"
        else:
            action = "Retry the query generation tool"
        return {
            "failure_log": log,
            "next_action": action
        } 

    def prompt_refinement(self, original_prompt, history):
        today = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d')

        with st.spinner(f"Refining a prompt"):
            sys_prompt, usr_prompt = get_prompt_refinement_prompt(original_prompt, today, history, self.language)
            response = self.boto3_client.converse(modelId=self.model, messages=usr_prompt, system=sys_prompt)
        self.update_tokens(response)
        parsed_json = parse_json_format(response['output']['message']['content'][0]['text'])
        refined_prompt = parsed_json.get("refined_prompt")
        with st.expander("Auto-refined Prompt (Click to expand)", expanded=False): 
            st.write(refined_prompt)
        return refined_prompt

    def query_generation(self, input: str): # dummy input
        table_names = self.db.get_usable_table_names()
        combined_log = """
        failure_log: {failure_log}
        failed_query: {failed_query}
        retry_hint: {search_result}
        """.format(failure_log=self.tool_state["failure_log"], failed_query=self.tool_state["failed_query"], search_result=self.tool_state["search_result"])

        table_summaries = self.get_table_summaries_by_similarities() # RAG    

        # Table Selection
        sys_prompt, usr_prompt = get_table_selection_prompt(table_summaries, self.prompt, self.samples, combined_log)
        response = self.boto3_client.converse(
            modelId=self.model,
            messages=usr_prompt,
            system=sys_prompt
        )
        self.update_tokens(response)
        # Loading Table Schemas
        table_names = response['output']['message']['content'][0]['text'].split(',')
        table_schemas = self.get_table_schemas(table_names)
        
        # SQL Query Generation
        sys_prompt, usr_prompt = get_query_generation_prompt(self.samples, self.dialect, table_schemas, self.language, self.prompt, combined_log)
        response = self.boto3_client.converse(
            modelId=self.model,
            messages=usr_prompt,
            system=sys_prompt
        )
        self.update_tokens(response)
        parsed_json = parse_json_format(response['output']['message']['content'][0]['text'])
        return parsed_json

    def validate_and_run_queries(self, generated_query: str):
        self.tool_state["initial_query"] = generated_query
        explain_query = self.get_explain_query(generated_query)
        try:
            query_plan = self.db.run(explain_query)
        except Exception as e:
            print(self.tool_state)
            return self.query_failure_handling(f"[E01] An error occurred while generating the EXPLAIN query: {str(e)}", generated_query)
    
        try:
            sys_prompt, usr_prompt = get_query_validation_prompt(self.dialect, query_plan, generated_query, self.language, self.prompt)
            response = self.boto3_client.converse(
                modelId=self.model,
                messages=usr_prompt,
                system=sys_prompt
            )
            self.update_tokens(response)
            
            parsed_json = parse_json_format(response['output']['message']['content'][0]['text'])
            query = parsed_json.get("final_query") 
            #output_columns = parsed_json.get("output_columns")

        except Exception as e:
            print(self.tool_state)
            return self.query_failure_handling(f"[E02] An issue unrelated to the query was encountered: {str(e)} (Model-related problem)", generated_query)
  
        try:
            result = self.db.run(query)

        except Exception as e:
            print(self.tool_state)
            return self.query_failure_handling(f"[E03] An error occurred while executing the final query: {str(e)}", query)

        if result is None or (isinstance(result, (list, tuple)) and len(result) == 0):
            self.tool_state["final_query"] = query
            self.tool_state["result_csv_file"] = "No data found from query execution" 
            self.tool_state["success"] = "True"
            return {"message": "Query executed successfully, but no matching data found."}
        
        try:
            csv_file, query_file, df = self.save_to_csv(result, query)
        except Exception as e:
            print(self.tool_state)
            return self.query_failure_handling(f"[E04] An error occurred while saving the results to CSV: {str(e)}", query)

        self.tool_state["final_query"] = query
        self.tool_state["sql_query_file"] = query_file
        self.tool_state["result_csv_file"] = csv_file
        if len(df) > 20:
            self.tool_state["partial_result"] = df[:20].to_dict(orient='records')
        else:
            self.tool_state["full_result"] = df.to_dict(orient='records')
        self.tool_state["success"] = "True"
        return {"message": "Query executed successfully"}

    def schema_explorer(self, keyword: str):
        query = {
            "size": 10, 
            "query": {
                "nested": {
                    "path": "columns",
                    "query": {
                        "match": {
                            "columns.col_desc": f"{keyword}"
                        }
                    },
                    "inner_hits": {
                        "size": 1, 
                        "_source": ["columns.col_name", "columns.col_desc"]
                    }
                }
            },
            "_source": ["table_name"]
        }
        response = self.schema_os_client.conn.search(
            index=self.schema_os_client.index_name,
            body=query
        )

        try:
            results = []
            table_names = set()  # To store unique table names
            if 'hits' in response and 'hits' in response['hits']:
                for hit in response['hits']['hits']:
                    table_name = hit['_source']['table_name']
                    table_names.add(table_name)  # Add table name to the set
                    for inner_hit in hit['inner_hits']['columns']['hits']['hits']:
                        column_name = inner_hit['_source']['col_name']
                        column_description = inner_hit['_source']['col_desc']
                        results.append({
                            "table_name": table_name,
                            "column_name": column_name,
                            "column_description": column_description
                        })
                        if len(results) >= 10:
                            break
                    if len(results) >= 10:
                        break
            self.tool_state['search_result'] += results
        except:
            self.tool_state['search_result'] += f"{keyword} not found"
        table_names_list = ', '.join(table_names)
        return {
            "keyword": keyword,
            "tables_hits": table_names_list
        }

    def tool_router(self, tool, callback):
        with st.spinner(f"Running Tool... ({tool['name']}, Retry: {self.retry})"):
            if tool['name'] == 'query_generation':
                res = self.query_generation(tool['input']['input'])
                tool_result = {"toolUseId": tool['toolUseId'], "content": [{"json": res}]}
            elif tool['name'] == 'validate_and_run_queries':
                res = self.validate_and_run_queries(tool['input']['generated_query'])
                tool_result = {"toolUseId": tool['toolUseId'], "content": [{"json": res}]}
                if 'failure_log' not in res:
                    self.retry = 0
                    self.tool_state["failure_log"] = "None"
                    self.tool_state["failed_query"] = "None"
                else:
                    self.retry += 1
            elif tool['name'] == 'schema_exploration':
                res = self.schema_explorer(tool['input']['keyword'])
                tool_result = {"toolUseId": tool['toolUseId'], "content": [{"json": res}]}
            else:
                tool_result = {"toolUseId": tool['toolUseId'], "content": [{"text": "Unknown tool name"}]}

            #print("[DEBUG] Tool_Result:", tool_result)
        callback.on_llm_new_result(json.dumps({
            "tool_name": tool['name'], 
            "content": tool_result["content"][0]
        }))

        tool_result_message = {"role": "user", "content": [{"toolResult": tool_result}]}

        return tool_result_message

class DB_Tool_Client:
    def __init__(self, model_info, config, language, sql_os_client, schema_os_client, prompt, history):
        self.model = model_info['model_id']
        self.region = model_info['region_name']
        self.dialect = config['dialect']
        self.language = language
        self.top_k = 5
        self.tool_config = self.load_tool_config()
        self.boto3_client = self.init_boto3_client(self.region)
        self.tokens = {'total_input_tokens': 0, 'total_output_tokens': 0, 'total_tokens': 0}
        self.db_tool = DB_Tools(self.tokens, config['uri'], self.dialect, self.model, self.region, sql_os_client, schema_os_client, language, prompt, history)
        self.prompt = self.db_tool.prompt

    def init_boto3_client(self, region: str):
        retry_config = Config(
            region_name=region,
            retries={"max_attempts": 10, "mode": "standard"}
        )
        return boto3.client("bedrock-runtime", region_name=region, config=retry_config)

    def load_tool_config(self):
        with open("./src/db_tool_config.json", 'r') as file:
            return json.load(file)

    def save_log(self):
        self.db_tool.tool_state['endtime'] = datetime.now().isoformat()
        self.db_tool.tool_state['token_used'] = self.tokens['total_tokens']

        log_entry = json.dumps(self.db_tool.tool_state, indent=4)
        logging.info(log_entry)
        
        for handler in logging.root.handlers:
            handler.flush()
            handler.close()

    def invoke(self, callback): 
        sys_prompt, usr_prompt = get_global_prompt(self.language, self.prompt)
        messages = usr_prompt
        stop_reason, message = stream_converse_messages(self.boto3_client, self.model, self.tool_config, messages, sys_prompt, callback, self.tokens)
        messages.append(message)

        while stop_reason == "tool_use":
            contents = message["content"]
            for c in contents:
                if "toolUse" not in c:
                    continue
                tool_use = c["toolUse"]
                message = self.db_tool.tool_router(tool_use, callback)
                messages.append(message)

            stop_reason, message = stream_converse_messages(self.boto3_client, self.model, self.tool_config, messages, sys_prompt, callback, self.tokens)
            messages.append(message)

        # Generating Final Response
        final_sys_prompt, final_usr_prompt = get_answer_generation_prompt(self.language, self.db_tool.tool_state, usr_prompt)
        stop_reason, message = stream_converse_messages(self.boto3_client, self.model, self.tool_config, final_usr_prompt, final_sys_prompt, callback, self.tokens)
        final_response = message['content'][0]['text']
        self.tokens['total_tokens'] = self.tokens['total_input_tokens'] + self.tokens['total_output_tokens']
        self.save_log()

        return final_response, self.tokens
