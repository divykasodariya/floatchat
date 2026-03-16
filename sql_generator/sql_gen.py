import os
import re
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
from google import genai
from sqlalchemy import create_engine, text
import pandas as pd
import json
# ========================
# 2. Parse metadata folder
# ========================
def parse_metadata_folder(folder_path):
    metadata_list = []
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".txt"):
            file_path = os.path.join(folder_path, file_name)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            table_match = re.search(r"### Metadata for Table: (\w+)", content)
            table_name = table_match.group(1) if table_match else file_name.replace(".txt", "")

            column_lines = [line.strip() for line in content.splitlines() if line.startswith("- ")]
            full_column_text = "\n".join(column_lines)

            metadata_list.append({
                "table": table_name,
                "full_text": full_column_text
            })
    return metadata_list

folder_path = "sql_generator/metadata"
metadata = parse_metadata_folder(folder_path)

# ========================
# 3. Initialize Chroma client
# ========================
client = chromadb.Client(Settings(
    persist_directory="chroma_db",
    anonymized_telemetry=False
))

# ========================
# 4. Define Chroma-compatible embedding function
# ========================
model = SentenceTransformer("all-MiniLM-L6-v2")

class STEmbedding(embedding_functions.EmbeddingFunction):
    def __init__(self, model):
        self.model = model
    def __call__(self, input):
        return model.encode(input).tolist()

st_embed = STEmbedding(model)

# ========================
# 5. Create or get collection
# ========================
collection_name = "metadata_collection"

if collection_name in [c.name for c in client.list_collections()]:
    collection = client.get_collection(name=collection_name)
else:
    collection = client.create_collection(
        name=collection_name,
        embedding_function=st_embed
    )

# ========================
# 6. Add metadata to collection (only first time)
# ========================
for i, table in enumerate(metadata):
    collection.add(
        documents=[table['full_text']],
        metadatas=[{"table": table['table']}],
        ids=[str(i)]
    )

# collection.persist()

# ========================
# 7. Retrieve relevant metadata
# ========================
def retrieve_metadata(query, top_k=3):
    results = collection.query(
        query_texts=[query],
        n_results=top_k
    )
    relevant = []
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        relevant.append({"table": meta['table'], "full_text": doc})
    return relevant

# ========================
# 8. Generate SQL using GPT (optional)
# ========================
#  another api key
gemini_client=client = genai.Client(api_key="-86l4")
def fire_sql(query, params=None):
    engine = create_engine("postgresql+psycopg2://root:atharva123@localhost:5432/ocean_data")
    cleaned_query = query.strip().rstrip(";")
    df = pd.read_sql(text(cleaned_query), engine, params=params)
    if 'm' in df.columns:
        df['datetime'] = pd.to_datetime(df['m'], unit='ms', utc=True)
    return json.loads(df.to_json(orient="records", date_format="iso"))

def generate_sql(user_query, top_k=3):
    # Step 1: Retrieve relevant metadata inside the function
    relevant_metadata = retrieve_metadata(user_query, top_k=top_k)
    
    if not relevant_metadata:
        return "No relevant metadata found for this query."

    # Step 2: Build metadata description for the prompt
    metadata_desc = ""
    for table in relevant_metadata:
        metadata_desc += f"Table: {table['table']}, Columns/Details:\n{table['full_text']}\n\n"

    # Step 3: Build the prompt for SQL generation
    prompt = f"""
            You are an expert PostgreSQL query generator. The user will ask for measurements of a parameter from the Argo float dataset. Follow these rules carefully when generating the SQL query:

            1. If the user does NOT mention pressure or depth:
            - First, group by exact time, latitude, and longitude to compute the average of the requested parameter.
            - This represents the measurement at that unique instant.

            2. Time-based aggregation rules:
            - If the date range is 6 days or less → return **daily averages**.
            - If the range is more than 6 days but less than or equal to 1 month → return **daily averages** (up to 31 records).
            - If the range is more than 1 month but less than or equal to 4 months → return **weekly averages**.
            - If the range is more than 4 months → return **15-day averages**.

            3. DATE_TRUNC rules:
            - PostgreSQL `DATE_TRUNC` only supports fixed units: 'second', 'minute', 'hour', 'day', 'week', 'month', 'quarter', 'year'.
            - **Never pass values like '15 days' directly into DATE_TRUNC.**
            - For custom intervals (e.g., 15-day), compute the grouping manually:
                ```
                DATE_TRUNC('day', time) - ((EXTRACT(DAY FROM DATE_TRUNC('day', time))::int % 15) * INTERVAL '1 day')
                ```
                Use this expression in both SELECT and GROUP BY when grouping by 15-day intervals.

            4. Filtering:
            - Exclude rows where the parameter, latitude, or longitude equals 99999.0.

            5. Latitude/Longitude bounds:
            - Only include rows where latitude and longitude are within the user-specified range.

            6. Grouping rules:
            - Every non-aggregated column in SELECT **must** appear in GROUP BY.
            - If you use an aggregate like `AVG(latitude)`, then do NOT include raw `latitude` in GROUP BY.

            7. Sorting rules:
            - If data is grouped, only order by the grouped time field and aggregated latitude/longitude if needed.
            - Never order by non-grouped, non-aggregated fields.

            8. The query must be generated in **one single line**, with no comments or explanations.

            9. Always include latitude and longitude in SELECT if the user query mentions a location.

            User Query: "{user_query}"
            Database Metadata: {metadata_desc}

            Generate the complete PostgreSQL query now.
            """


    # Step 4: Generate SQL using Gemini
    response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    sql_query = response.text.strip()   # remove leading/trailing whitespace
    sql_query = sql_query.replace("```sql", "").replace("```", "").replace("\n", "").strip()
    return (sql_query, fire_sql(sql_query))


def ask_llm(prompt):
    response = gemini_client.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt
    )
    return response.text



