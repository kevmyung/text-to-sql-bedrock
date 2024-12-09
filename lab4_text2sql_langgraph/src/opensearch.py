import os
import json
import yaml
import boto3
import time
import streamlit as st
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from .common_utils import sample_query_indexing, schema_desc_indexing
from collections import namedtuple
from dotenv import load_dotenv

Document = namedtuple('Document', ['page_content', 'metadata'])

class OpenSearchClient:
    def __init__(self, region_name, index_name, mapping_name, vector, text, output):
        config = self.load_opensearch_config()

        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, region_name, 'aoss')

        collection_endpoint = config['COLLECTION_ENDPOINT']
        host = collection_endpoint.replace("https://", "").split(':')[0]

        self.index_name = index_name
        self.config = config
        self.vector = vector
        self.text = text
        self.output = output

        self.mapping = {"settings": config['settings'], "mappings": config[mapping_name]}
        self.conn = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20
        )
        
    def load_opensearch_config(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        dotenv_path = os.path.join(project_root, '.env')
        load_dotenv(dotenv_path)

        config_path = os.path.join(current_dir, "opensearch.yml")
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        
        config['COLLECTION_ENDPOINT'] = os.getenv('COLLECTION_ENDPOINT')
        return config        


    def create_index(self):
        index_name = self.index_name
        if not self.conn.indices.exists(index=index_name):
            print(f"Index {index_name} does not exist. Creating now...")
        else:
            self.conn.indices.delete(index=index_name)
            print(f"Existing index '{index_name}' has been deleted. Create new one.")
            time.sleep(2)
        self.conn.indices.create(index_name, body=self.mapping)


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

    def vector_search(self, input_text):
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

        result = self.os_client.conn.search(index=self.os_client.index_name, body=semantic_query)
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