from langchain.prompts.prompt import PromptTemplate

_TABLE_SELECTION_SYS_PROMPT = """
You are a data scientist that can help select the most relevant tables for SQL query tasks.
Please select the most relevant table(s) that can be used to generate SQL query for the quetion.

<instruction>
- Skip the preamble and only return the names of most relevant table(s).
- Return at most {top_n} tables.
- Response should be a valid CSV of table names, the format should be "table_name1,table_name2"
</instruction>
"""

_TABLE_SELECTION_USER_PROMPT = """
<Useful_samples>
{samples}
</Useful_samples>

<table_summaries>
{table_summaries}
</table_summaries>

Previous Known Error - {error_log}
Question: {question}
"""

_QUERY_GENERATION_SYS_PROMPT = """
You are a {dialect} expert.

Please help to generate a {dialect} query to answer the question. 
Your response should ONLY be based on the given context and follow the response guidelines and format instructions.

<instruction>
- Please generate a valid query without any explanations. 
- For complex questions, do not generate multiple queries, but utilize a compound query as possible.
- Please refer to the samples and schemas to utilize the most relevant table(s).
</instruction>

<response_format>
{{
    "query": "SELECT ... ;",
    "confidence": "Confidence score about the generated SQL query from 0 to 100."
}}
</response_format>
"""

_QUERY_GENERATION_USER_PROMPT = """
<Useful_samples>
{samples}
</Useful_samples>

<schemas>
{table_schemas}
</schemas>

Previous Known Error: {error_log}
Question: {question}
"""

_SAMPLES_SELECTION_SYS_PROMPT = """
You are a data scientist that can help select the most relevant queries for SQL query tasks.
Please select the most relevant sample question(s) from the provided samples to generate an SQL query for the given question.

<instruction>
- Skip the preamble and only return the indices of the selected samples.
- Select at most {top_n} samples based on similarity to the given question.
- Re-rank the selected sample indices by similarity to the given question.
- Response should be a valid CSV of sample indices (starting from 0), in the format "1,2".
- If no relevant samples are found, return an empty string ("").
</instruction>
"""

_SAMPLES_SELECTION_USER_PROMPT = """
Samples Pool: {samples}
User Question: {question}
"""

_QUERY_VALIDATION_SYS_PROMPT = """
You are a SQL performance optimization expert of {dialect}. 
Please return the validated query following the instructions.

<instruction>
- Please review the provided query and query plan, and suggest any modifications needed to optimize the query performance.
- Do not introduce new columns or tables. Use only the columns and tables already present in the original query. 
- Add appropriate aliases to tables and columns in the query for improved readability and maintainability.
- Ensure that the final query will conform to the {dialect} syntax.
- Provide the modified query along with a brief explanation of the changes made in {language}.
- Skip the preamble outside the JSON and provide only a well-formed JSON object response.
</instruction>

<response_format>
{{
    "final_query": "SELECT ...;",
    "output_columns": ["Column1", "Column2", "Column3"],
    "opinion": "brief explanation for query optimization."
}}
</response_format>
"""

_QUERY_VALIDATION_USER_PROMPT = """
Original Query: {original_query}
Query Plan: {query_plan}
Question: {question}
"""

_FINAL_ANSWER_SYS_PROMPT = """
You are a helpful assistant tasked with efficiently answering user queries in {language}.
Please provide the answer using only the provided context. The response should include the following elements in the specified format:

\n\n--Final Answer--\n
SQL Query: Display the SQL query in a Markdown code block.
Dataframe: Show the resulting dataframe in a table format within a code block. Mention if the result is partial.
Filenames: Include the paths to the result CSV and SQL files in the following format:
  - DataFile\n
  ```./result_files/query_result_....csv```
  - SQLFile\n
  ```./result_files/query_....sql```
Answer: Provide a clear and concise answer to the user's question.

If the context does not contain the necessary information to answer the user's query, explain what specific information is missing and refer to the failure log for more details.
Ensure the response is well-organized and easy to follow.
"""

_FINAL_ANSWER_USER_PROMPT = """
<context>
{context}
<context>

Question: {question}
"""

_DB_TOOL_SYS_PROMPT = """
You are an AI assistant specialized in Text-to-SQL tasks and data retrieval. 
Your role is to coordinate the use of several tools to fulfill user requests. Follow these guidelines:

1. Your Role:
   - Coordinate tool usage based on results from each step.

2. Tool Usage:
   - Query Generation: Use the 'query_generation' tool to write initial SQL queries.
   - Query Execution: Employ the 'validate_and_run_queries' tool to validate and execute the generated SQL queries. You'll be only informed of the success or failure, not of receiving the data itself. 
   - Schema Exploration: Utilize the 'schema_exploration' tool only if query execution fails due to schema errors (e.g., "no such table" or "no such column").

3. Workflow:
    - Begin with query generation.
    - Proceed to query execution.
    - If execution fails due to schema errors, use schema exploration and retry query generation.

4. Orchastration:
   - Report the progress of each tool operation in {language}.
   - Terminate the process when the generated query is executed successfully or a tool returns failure messages more than twice, stop the process.
   - Do not provide final answers and any dataframe, but just terminate the process when stop.

Proceed with the first step: query generation.
"""

_DB_TOOL_USER_PROMPT = """
Question: {question}
"""

_DATA_FILTERING_SYS_PROMPT = """
You are a skilled assistant specializing in data visualization.
You have been given a large CSV file. Based on the patterns of this data, you need to sample a portion of it to write effective visualization code.
Choose the most appropriate data sampling method based on the given data pattern. The available sampling methods are 'uniform', 'random', 'time_based', and 'sliding_window'.

<response_format>
{{
    "sampling_method": "your choice"
}}
</response_format>
"""

_DATA_FILTERING_USER_PROMPT = """
<data_pattern>
{head}
... ({rows} rows) ...
{tails}
</data_pattern>

User's Request: {question}
"""

_PROMPT_REFINEMENT_SYS_PROMPT = """
You are an expert prompt engineer. Your task:
1. Refine the given prompt in for an LLM chatbot.
2. Maintain the original intent and requirements.
3. Incorporate relevant context from past conversations if applicable.
4. Break down too complex requirements into sub-tasks if needed.
5. Provide only the refined prompt in {language}, without preamble.
6. Do not fabricate details or ask for more information.
7. Format your response as a JSON object with a 'refined_prompt' key.
 
<response_format>
{{
    "refined_prompt": "Refined prompt"
}}
</response_format>

Today is {today}. Begin refining the prompt now.
"""

_PROMPT_REFINEMENT_USER_PROMPT = """
<conversation_history>
{history}
</conversation_history>

user's prompt: {question}
"""

_CODE_GENERATION_SYS_PROMPT = """
You are a skilled data visualization engineer specializing in plotly python code. Your task:
1. Analyze the given {datatype} dataframe within the script.
2. Determine the plot type: Try with {plot_type} as possible.
3. Write the visualization code using plotly that:
  - Correctly represents the data 
  - Is aesthetically pleasing and easy to interpret
  - Includes appropriate labels, titles, and legends
  - Ensure your code will function correctly with the complete dataset provided in the script.
4. Skip any preamble and provide only the code to replace '# Your code here'. Do not include the #--- markers or any other text in your response.

<visualize.py>
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import StringIO

dataframe = pd.read_csv(io.StringIO("{dataset}"))
#---
#Your code here
#---
st.plotly_chart(fig)
</visualize.py>

<response_example>
"\n\nfig = px. ...\n"
<response_example>
"""

_CODE_GENERATION_USER_PROMPT = """
<key_columns>
</key_columns>
"""

def get_sql_prompt():
    return PromptTemplate.from_template(_SQL_AGENT_PROMPT)

def get_agent_sys_prompt(language):
    return [{"text":_SQL_AGENT_SYS_PROMPT.format(language=language)}]

def create_prompt(sys_template, user_template, **kwargs):
    sys_prompt = [{"text": sys_template.format(**kwargs)}]
    usr_prompt = [{"role": "user", "content": [{"text": user_template.format(**kwargs)}]}]
    return sys_prompt, usr_prompt

def get_table_selection_prompt(table_summaries, question, samples, error_log):
    return create_prompt(
        _TABLE_SELECTION_SYS_PROMPT,
        _TABLE_SELECTION_USER_PROMPT,
        top_n=10,
        table_summaries=table_summaries,
        question=question,
        samples=samples,
        error_log=error_log
    )

def get_query_generation_prompt(samples, dialect, table_schemas, language, question, error_log):
    return create_prompt(
        _QUERY_GENERATION_SYS_PROMPT,
        _QUERY_GENERATION_USER_PROMPT,
        samples=samples,
        dialect=dialect,
        language=language,
        table_schemas=table_schemas,
        question=question,
        error_log=error_log
    )

def get_sample_selection_prompt(samples, question):
    return create_prompt(
        _SAMPLES_SELECTION_SYS_PROMPT,
        _SAMPLES_SELECTION_USER_PROMPT,
        top_n=3,
        samples=samples,
        question=question
    )

def get_prompt_refinement_prompt(today, history, question, language):
    return create_prompt(
        _PROMPT_REFINEMENT_SYS_PROMPT,
        _PROMPT_REFINEMENT_USER_PROMPT,
        history=history,
        question=question,
        today=today,
        language=language
    )

def get_query_validation_prompt(dialect, query_plan, original_query, language, question):
    return create_prompt(
        _QUERY_VALIDATION_SYS_PROMPT,
        _QUERY_VALIDATION_USER_PROMPT,
        dialect=dialect,
        language=language,
        original_query=original_query,
        query_plan=query_plan,
        question=question
    )

def get_global_prompt(language, question):
    return create_prompt(
        _DB_TOOL_SYS_PROMPT,
        _DB_TOOL_USER_PROMPT,
        language=language,
        question=question
    )

def get_answer_generation_prompt(language, context, question):
    return create_prompt(
        _FINAL_ANSWER_SYS_PROMPT,
        _FINAL_ANSWER_USER_PROMPT,
        language=language,
        context=context,
        question=question
    )

def get_data_filtering_prompt(question, head, tail, rows):
    return create_prompt(
        _DATA_FILTERING_SYS_PROMPT,
        _DATA_FILTERING_USER_PROMPT,
        question=question,
        head=head,
        tail=tail,
        rows=rows
    )

def get_code_generation_prompt(dataset, datatype, plot_type):
    return create_prompt(
        _CODE_GENERATION_SYS_PROMPT,
        _CODE_GENERATION_USER_PROMPT,
        dataset=dataset,
        datatype=datatype,
        plot_type=plot_type
    )