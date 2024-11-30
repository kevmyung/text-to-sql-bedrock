import os
import json
import yaml
import boto3
import streamlit as st
from opensearchpy import OpenSearch, RequestsHttpConnection
from .common_utils import sample_query_indexing, schema_desc_indexing
from .ssm import parameter_store
from collections import namedtuple

Document = namedtuple('Document', ['page_content', 'metadata'])

class OpenSearchClient:
    def __init__(self, region_name, index_name, mapping_name, vector, text, output):
        pm = parameter_store(region_name)
        config = self.load_opensearch_config()
        self.index_name = index_name
        self.config = config
        domain_endpoint = pm.get_params(key="chatbot-opensearch_domain_endpoint", enc=False)
        self.endpoint = f"https://{domain_endpoint}"
        self.http_auth = (pm.get_params(key="chatbot-opensearch_user_id", enc=False), pm.get_params(key="chatbot-opensearch_user_password", enc=True))
        self.vector = vector
        self.text = text
        self.output = output
        self.mapping = {"settings": config['settings'], "mappings": config[mapping_name]}
        self.conn = OpenSearch(
            hosts=[{'host': self.endpoint.replace("https://", ""), 'port': 443}],
            http_auth=self.http_auth, 
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        ) 
        
    def load_opensearch_config(self):
        file_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(file_dir, "opensearch.yml")

        with open(config_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)

    def is_index_present(self):
        return self.conn.indices.exists(self.index_name)
    
    def create_index(self):
        self.conn.indices.create(self.index_name, body=self.mapping)

    def delete_index(self):
        if self.is_index_present():
            self.conn.indices.delete(self.index_name)


class OpenSearchVectorRetriever:
    def __init__(self, os_client, region_name, k=5):
        self.emb_model = "amazon.titan-embed-text-v2:0"
        self.os_client = os_client
        self.region = region_name 
        self.k = k

    def _embedding(self, input_text):
        boto3_client = boto3.client("bedrock-runtime", region_name=self.region)
        response = boto3_client.invoke_model(
                modelId=self.emb_model,
                body=json.dumps({"inputText": input_text})
            )

        return json.loads(response['body'].read())['embedding']

    def vector_search(self, input_text, index_name):
        embedding = self._embedding(input_text)
        semantic_query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "knn": {
                                self.os_client.vector: {
                                    "vector": embedding,
                                    "k": self.k,
                                }
                            }
                        },
                    ]
                }
            },
            "size": self.k
        }

        result = self.os_client.conn.search(index=index_name, body=semantic_query)

        documents = []
        for hit in result['hits']['hits']:
            source = hit['_source']
            page_content = {k: source[k] for k in self.os_client.output if k in source}
            documents.append(Document(page_content=json.dumps(page_content), metadata={}))

        return documents
    
def initialize_os_client(enable_flag, client_params, indexing_function, lang_config):
    if enable_flag:
        client = OpenSearchClient(**client_params)
        indexing_function(client, lang_config)
    else:
        client = ""
    return client

def init_opensearch(region_name, lang_config):
    with st.sidebar:
        enable_rag_query = st.sidebar.checkbox(lang_config['rag_query'], value=True, disabled=True)
        sql_os_client = initialize_os_client(
            enable_rag_query,
            {
                "region_name": region_name,
                "index_name": 'example_queries',
                "mapping_name": 'mappings-sql',
                "vector": "input_v",
                "text": "input",
                "output": ["input", "query"]
            },
            sample_query_indexing,
            lang_config
        )

        enable_schema_desc = st.sidebar.checkbox(lang_config['schema_desc'], value=True, disabled=True)
        schema_os_client = initialize_os_client(
            enable_schema_desc,
            {
                "region_name": region_name,
                "index_name": 'schema_descriptions',
                "mapping_name": 'mappings-detailed-schema',
                "vector": "table_summary_v",
                "text": "table_summary",
                "output": ["table_name", "table_summary"]
            },
            schema_desc_indexing,
            lang_config
        )

    return sql_os_client, schema_os_client