# main_app.py
import google.generativeai as genai
import subprocess
import json
import os
# Configure Gemini
genai.configure(api_key='AIzaSyAOdvQJsdxV3u3hvkrxQtwhbUPH48gC_4Q')  # put your actual key here

# Create model (like a "client")
model = genai.GenerativeModel("gemini-1.5-flash")  # or gemini-1.5-pro


def run_query_via_mcp(sql_query):
    """Sends an SQL query to the MCP Server and returns the results."""
    try:
        server_process = subprocess.Popen(
            ['python', 'mcp_server.py'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "run_query",
            "params": {
                "sql_query": sql_query
            }
        }

        server_process.stdin.write(json.dumps(request) + '\n')
        server_process.stdin.flush()

        response_line = server_process.stdout.readline().strip()
        response = json.loads(response_line)

        server_process.terminate()
        return response.get('result', {})

    except Exception as e:
        return {"error": f"Failed to communicate with MCP server: {str(e)}"}

metadata_str = (

    "Table Metadata:\n"
    "Table name: argo_data\n"
    "1. platform_code: Unique identifier of the Argo float (string).\n"
    "2. datetime: Timestamp of measurement in UTC (format YYYY-MM-DDTHH:MM:SSZ).\n"
    "3. latitude: Latitude of measurement in degrees north (-90 to 90).\n"
    "4. longitude: Longitude of measurement in degrees east (-180 to 180).\n"
    "5. depth: Depth of measurement in meters (0 to 2000 typically).\n"
    "6. temperature: Water temperature in degree Celsius (-2 to 40°C typical).\n"
    "7. salinity: Salinity of water in PSU (0 to 40 PSU typical).\n"
    "8. pressure: Pressure in decibar (0 to 2000 dbar typical).\n"
    "9. oxygen: Dissolved oxygen in ml/L (0 to 10 typical).\n"
    "10. chlorophyll: Chlorophyll concentration in mg/m3 (0 to 10 typical).\n"
    "11. oxygen_saturation: Oxygen saturation percentage (OSAT %, 0 to 100).\n"
    "12. source_file: Original CSV source file.\n"
    "\nBGC mapping:\n"
    "- DOX1, DOX12, DOX22, DOX23, DOXY = oxygen-related BGC measurements\n"
    "- FLU2, CPHL = chlorophyll-related BGC measurements\n"
    "- OSAT = oxygen saturation\n"
    "\nGeographic info:\n"
    "- Latitude: -90 to 90, Longitude: -180 to 180\n"
    "- Common regions: Indian Ocean, Pacific Ocean, Atlantic Ocean, Southern Ocean, Arctic Ocean\n"
    "\nDomain terms:\n"
    "- Argo float, profiling float, BGC, CTD sensor, oceanographic profile, FloatChat, biogeochemical data\n"
    "This metadata describes the database columns, units, typical ranges, BGC mapping, geographic context, and domain jargon.\n"
)
def handle_query(query):
    prompt = f"""
    You are an expert in Oceanography and mySQL query generation.
    Your task is to convert the user's natural language query into a valid mySQL query using the provided table metadata.
    Follow these strict rules without exception:

    1. Do NOT generate any DDL statements (CREATE, DROP, ALTER, etc.).
    2. Return ONLY the SQL query. No explanations, no comments, no markdown, no extra text. If you output anything else, you have failed the task.
    3. Depth handling:
      - If the user explicitly specifies a depth → include depth in SELECT and GROUP BY.
      - If the user does NOT specify depth → DO NOT include depth in SELECT or GROUP BY. Instead, average the requested parameter across all depths at that time/location.
    4. Time aggregation rules:
      - 7 days or less → daily averages using STRFTIME('%Y-%m-%d', datetime).
      - About 1 month → weekly averages using STRFTIME('%Y-%m-%d', datetime).
      - More than 1 month → monthly averages using STRFTIME('%Y-%m-%d', datetime)
      - Always return ALL periods in the requested range.
    5. Only include rows where the requested parameter (salinity, temperature, pressure) IS NOT NULL.
    6. Do NOT average latitude or longitude unless explicitly requested.
    7. Use ONLY the columns in the provided metadata. Do not assume any other columns exist.
    8. Always includen platform_code, latitude and longitude in your query.
    9. If you fail any rule, your output will be discarded.

    --- Few-shot examples ---

    # Example 1: Depth not specified, weekly average
    User query: "Show me salinity profiles near the equator in September 2024"
    SQL:
    SELECT
    platform_code,
    latitude,
    longitude,
    DATE_FORMAT(datetime, '%Y-%m-%d') AS week_of_year,
    AVG(salinity) AS avg_salinity
    FROM argo_data
    WHERE
    latitude BETWEEN -5 AND 5
    AND datetime >= '2024-09-01 00:00:00'
    AND datetime < '2024-10-01 00:00:00'
    AND salinity IS NOT NULL
    GROUP BY
    week_of_year, platform_code, latitude, longitude
    ORDER BY
    week_of_year;


    # Example 2: Depth specified
    User query: "Show me salinity at 10m depth near the equator in September 2024"
    SQL:
    SELECT
    platform_code,
    latitude,
    longitude,
    DATE_FORMAT(datetime, '%Y-%m-%d') AS week_of_year,
    depth,
    AVG(salinity) AS avg_salinity
    FROM argo_data
    WHERE
    depth = 10
    AND latitude BETWEEN -5 AND 5
    AND datetime >= '2024-09-01 00:00:00'
    AND datetime < '2024-10-01 00:00:00'
    AND salinity IS NOT NULL
    GROUP BY
    week_of_year, depth, platform_code, latitude, longitude
    ORDER BY
    week_of_year, depth;

    # Example 3: Monthly aggregation
    User query: "Show me monthly temperature near 20N, 50E for the past 6 months"
    SQL:
    SELECT
    platform_code,
    latitude,
    longitude,
    DATE_FORMAT(datetime, '%Y-%m') AS month,
    AVG(temperature) AS avg_temperature
    FROM argo_data
    WHERE
    latitude BETWEEN 19 AND 21
    AND longitude BETWEEN 49 AND 51
    AND datetime >= '2024-03-01 00:00:00'
    AND datetime <= '2024-08-31 23:59:59'
    AND temperature IS NOT NULL
    GROUP BY
    month, platform_code, latitude, longitude
    ORDER BY
    month;


    --- End of examples ---

    metadata: {metadata_str}
    user query: {query}
    """

    response = model.generate_content(prompt)

    sql_query = response.text.strip()
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
    return sql_query


def main():
    user_question = "Show me salinity profiles near the equator in September 2024"

    print("🔧 Generating SQL query...")
    sql_query = handle_query(user_question)
    print(f"📋 Generated SQL: {sql_query}")

    print("⚡ Executing query via MCP Server...")
    result = run_query_via_mcp(sql_query)

    if "error" in result:
        print(f"❌ Error: {result['error']}")
    elif result.get("success"):
        data = result["data"]
        print(f"✅ Query successful! Found {len(data)} records.")
        for i, row in enumerate(data[:3]):
            print(f"Row {i+1}: {row}")
    else:
        print("❓ Unexpected response from server:", result)


if __name__ == "__main__":
    main()
