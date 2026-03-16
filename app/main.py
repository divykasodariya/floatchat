from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List
# Import your separate modules
from intent_classifi.classifier import classify_intent
from sql_generator.sql_gen import generate_sql
from sql_generator.sql_gen import fire_sql
from sql_generator.sql_gen import ask_llm
app = FastAPI(title="Intent + SQL Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or specify ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def read_root():
    return {"message": "Hello World"}

class QueryRequest(BaseModel):
    text: str

@app.post("/process_query")
async def process_query(request: QueryRequest):
    # Step 1: Detect intent
    intent_result = classify_intent(request.text)
    predicted_label = intent_result['predicted_label']

    response = {
        "query": request.text,
        "intent": predicted_label
    }

    # Step 2: If it's a database query, generate SQL
    if predicted_label == "Database Query":
        sql_query, data_json = generate_sql(request.text)
        prompt_template="""
        You are an assistant designed to analyze oceanographic data and return responses strictly in JSON format for frontend rendering.

### Rules:
1. You must ONLY respond with a valid JSON object. No extra text, explanations, or commentary outside JSON.
2. The JSON object must have the following structure:
   {{
     "visualization_type": "chart" | "table" | "none",
     "chart": {{
       "type": "line" | "bar" | "scatter",
       "x_axis": "string",
       "y_axis": "string",
       "data_points": [
         {{"x": "value1", "y": number1 }},
         {{ "x": "value2", "y": number2 }}
       ]
     }},
     "table": {{
       "columns": ["column_name_1", "column_name_2"],
       "rows": [
         ["value1", value2],
         ["value3", value4]
       ]
     }},
     "summary": "A short natural language summary of the data and insights."
   }}

3. Fill either the **chart** or the **table** object depending on the most suitable visualization type.  
   - If you use `"chart"`, leave `"table": {{}}` empty.
   - If you use `"table"`, leave `"chart": {{}}` empty.
4. If there is not enough relevant data to answer, respond with:
   {{
     "visualization_type": "none",
     "summary": "The dataset does not contain enough information to answer this question."
   }}
5. Do NOT include any extra keys, comments, or text outside this JSON structure.

### Input:
User query: {}
Relevant data (JSON): {}

### Output:
Return only the valid JSON response.
        """
        prompt=prompt_template.format(request.text, data_json)
        floatchat_response=ask_llm(prompt=prompt)
        response['floatchat_response'] = floatchat_response
        response['sql_query']=sql_query
        response['data']=data_json
    return response

@app.get("/get-trajectory")
async def get_trajectory(text: int):
    query = f"""
    SELECT DISTINCT ON (DATE(time)) 
        time AS obs_time, latitude, longitude
    FROM temp
    WHERE platform_number = {text}
      AND latitude BETWEEN -90 AND 90
      AND longitude BETWEEN -180 AND 180
    ORDER BY DATE(time), time DESC
    LIMIT 35;
    """
    return {"response": fire_sql(query)}

@app.get("/get-all-floats")
async def get_all_floats():
    query=f"""
        SELECT platform_number, latitude, longitude, platform_type, time
        FROM latest_float_positions
        ORDER BY platform_number;
    """
    return {"response": fire_sql(query)}
class FloatDataRequest(BaseModel):
    floatNumbers: List[int]
    startTime: str
    endTime: str
    parameters: List[str]  # ["temp", "psal", "doxy"]

# Allowed params mapped to their respective table names
PARAM_TO_TABLE = {
    "temp": "temp",
    "psal": "psal",
    "doxy": "doxy",
    "nitrate":"nitrate",
    "chla":"chla"
}
@app.post("/compare-floats")
async def compare_floats(request: FloatDataRequest):
    valid_params = [p.lower() for p in request.parameters if p.lower() in PARAM_TO_TABLE]
    if not valid_params:
        raise HTTPException(status_code=400, detail="Select at least one valid parameter: temp, psal, doxy, nitrate, chla.")

    select_case_parts = [f"MAX(CASE WHEN source = '{p.upper()}' THEN value END) AS {p}" for p in valid_params]
    select_case_sql = ",\n    ".join(select_case_parts)

    union_parts = []
    params = {}
    for i, p in enumerate(valid_params):
        table_name = PARAM_TO_TABLE[p]
        float_key = f"float_numbers_{i}"
        start_key = f"start_time_{i}"
        end_key = f"end_time_{i}"
        
        union_parts.append(f"""
        SELECT
            platform_number,
            platform_type,
            time,
            latitude,
            longitude,
            AVG({p}) AS value,
            '{p.upper()}' AS source
        FROM {table_name}
        WHERE platform_number = ANY(:{float_key})
          AND time BETWEEN :{start_key} AND :{end_key}
        GROUP BY platform_number, platform_type, time, latitude, longitude
        """)
        
        # Add parameters for this UNION block
        params[float_key] = request.floatNumbers
        params[start_key] = request.startTime
        params[end_key] = request.endTime

    union_sql = "\n    UNION ALL\n".join(union_parts)

    final_sql = f"""
    SELECT
        platform_number,
        platform_type,
        time,
        latitude,
        longitude,
        {select_case_sql}
    FROM (
        {union_sql}
    ) AS combined
    GROUP BY platform_number, platform_type, time, latitude, longitude
    ORDER BY platform_number, time;
    """

    return fire_sql(final_sql, params)

@app.get('/get-float-data')
async def get_data(float_number: str):
    getData=f"""
    WITH latest_days AS (
    SELECT DISTINCT DATE(time) as measurement_date
    FROM temp
    WHERE platform_number = {float_number}
    ORDER BY measurement_date DESC
    LIMIT 10
    )
    SELECT 
        ld.measurement_date,
        (SELECT AVG(temp) FROM temp WHERE platform_number = {float_number} AND DATE(time) = ld.measurement_date) as avg_temp,
        (SELECT AVG(chla) FROM chla WHERE platform_number = {float_number} AND DATE(time) = ld.measurement_date) as avg_chla,
        (SELECT AVG(psal) FROM psal WHERE platform_number = {float_number} AND DATE(time) = ld.measurement_date) as avg_psal,
        (SELECT AVG(doxy) FROM doxy WHERE platform_number = {float_number} AND DATE(time) = ld.measurement_date) as avg_doxy
    FROM latest_days ld
    ORDER BY ld.measurement_date DESC;
    """
    return fire_sql(getData)


@app.get("/view-profile")
async def view_profile(float_number: str, time: str):
    view_profile_query=f"""
    -- Use predefined depth levels that match typical Argo float resolution
    SELECT 
    pres as depth,
    ROUND(temp::numeric, 3) as temperature,
    ROUND(chla::numeric, 5) as chlorophyll,
    ROUND(ph_in_situ_total::numeric, 3) as ph,
    ROUND(nitrate::numeric, 3) as nitrate,
    ROUND(doxy::numeric, 3) as oxygen,
    ROUND(psal::numeric, 3) as salinity
    FROM (
    SELECT 
        t.pres, t.temp, c.chla, p.ph_in_situ_total, n.nitrate, d.doxy, ps.psal,
        -- Only keep measurements at standard depth levels
        CASE 
        WHEN t.pres <= 10 THEN t.pres::integer  -- Keep all surface measurements
        WHEN t.pres <= 100 THEN t.pres::integer / 5 * 5  -- Round to nearest 5m
        WHEN t.pres <= 500 THEN t.pres::integer / 10 * 10  -- Round to nearest 10m
        ELSE t.pres::integer / 50 * 50  -- Round to nearest 50m
        END as depth_group
    FROM temp t
    LEFT JOIN chla c ON t.platform_number = c.platform_number AND t.time = c.time AND t.pres = c.pres
    LEFT JOIN ph p ON t.platform_number = p.platform_number AND t.time = p.time AND t.pres = p.pres
    LEFT JOIN nitrate n ON t.platform_number = n.platform_number AND t.time = n.time AND t.pres = n.pres
    LEFT JOIN doxy d ON t.platform_number = d.platform_number AND t.time = d.time AND t.pres = d.pres
    LEFT JOIN psal ps ON t.platform_number = ps.platform_number AND t.time = ps.time AND t.pres = ps.pres
    WHERE t.platform_number = {float_number} 
        AND DATE(t.time) = '{time}'
        AND t.pres <= 2000
    ) sub
    -- Only keep one measurement per depth group
    WHERE pres = depth_group
    ORDER BY depth;
    """
    return fire_sql(view_profile_query)



@app.get("/view-profile")
async def view_profile(float_number: str, time: str = None):
    """
    Get profile data for a specific float with depth and all available parameters
    """
    try:
        # Get the most recent profile if no time specified
        if not time:
            time_query = f"""
            SELECT MAX(time) as latest_time 
            FROM temp 
            WHERE platform_number = {float_number}
            """
            time_result = fire_sql(time_query)
            if time_result and len(time_result) > 0:
                time = time_result[0]['latest_time']
            else:
                return {"error": "No data found for this float"}
        
        # Query to get profile data with all parameters
        profile_query = f"""
        WITH profile_data AS (
            SELECT 
                t.depth,
                t.temp as temperature,
                p.psal as salinity,
                c.chla as chlorophyll,
                n.nitrate,
                ph.ph,
                d.doxy as oxygen
            FROM temp t
            LEFT JOIN psal p ON t.platform_number = p.platform_number 
                AND t.time = p.time 
                AND t.depth = p.depth
            LEFT JOIN chla c ON t.platform_number = c.platform_number 
                AND t.time = c.time 
                AND t.depth = c.depth
            LEFT JOIN nitrate n ON t.platform_number = n.platform_number 
                AND t.time = n.time 
                AND t.depth = n.depth
            LEFT JOIN ph ON t.platform_number = ph.platform_number 
                AND t.time = ph.time 
                AND t.depth = ph.depth
            LEFT JOIN doxy d ON t.platform_number = d.platform_number 
                AND t.time = d.time 
                AND t.depth = d.depth
            WHERE t.platform_number = {float_number}
                AND t.time = '{time}'
                AND t.depth IS NOT NULL
        )
        SELECT * FROM profile_data
        WHERE depth IS NOT NULL
        ORDER BY depth ASC;
        """
        
        result = fire_sql(profile_query)
        
        # Get float metadata
        metadata_query = f"""
        SELECT platform_number, platform_type, latitude, longitude, time
        FROM latest_float_positions 
        WHERE platform_number = {float_number}
        LIMIT 1;
        """
        metadata = fire_sql(metadata_query)
        
        return {
            "data": result,
            "profile_date": time,
            "metadata": metadata[0] if metadata else None
        }
        
    except Exception as e:
        return {"error": f"Failed to fetch profile data: {str(e)}"}


@app.get('/get-danger')
async def danger_zone():
    queryDanger="select * from indian_ocean_combined;"
    return fire_sql(query=queryDanger)