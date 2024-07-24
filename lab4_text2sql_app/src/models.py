from typing import Dict, List, Union
from langchain_aws import ChatBedrock
from langchain_community.embeddings import BedrockEmbeddings

class ChatModel:
    def __init__(self, model_info: Dict, model_kwargs: Dict):
        self.model_info = model_info
        self.model_id = self.model_info["model_id"]
        self.model_kwargs = model_kwargs
        self.llm = ChatBedrock(model_id=self.model_id, region_name=self.model_info['region_name'], model_kwargs=model_kwargs, streaming=True)
        self.emb = BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0", region_name=self.model_info['region_name'], model_kwargs={"dimensions":1024})
    
    def format_prompt(self, prompt: str) -> Union[str, List[Dict]]:
        model_info = self.model_info
        if model_info.get("input_format") == "text":
            return prompt
        elif model_info.get("input_format") == "list_of_dicts":
            prompt_text = {"type": "text", "text": prompt}
            return [prompt_text]
        else:
            raise ValueError(f"Unsupported input format for model: {self.model_id}")
        
def calculate_cost_from_tokens(tokens, model_id):
    PRICING = {
        "anthropic.claude-3-sonnet-20240229-v1:0": {
            "input_rate": 0.003,
            "output_rate": 0.015
        },
        "anthropic.claude-3-5-sonnet-20240620-v1:0": {
            "input_rate": 0.003,
            "output_rate": 0.015
        },
        "anthropic.claude-3-haiku-20240307-v1:0": {
            "input_rate": 0.00025,
            "output_rate": 0.00125
        },
    }
    if model_id not in PRICING:
        return 0.0, 0.0, 0.0 
    
    input_cost = tokens['total_input_tokens'] / 1000 * PRICING[model_id]['input_rate']
    output_cost = tokens['total_output_tokens'] / 1000 * PRICING[model_id]['output_rate']
    total_cost = input_cost + output_cost

    return input_cost, output_cost, total_cost


