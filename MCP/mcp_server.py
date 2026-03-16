# mcp_server.py
import mysql.connector
import sys
import json
import traceback
from mysql.connector import Error

# === DATABASE CONFIGURATION - UPDATE THESE VALUES ===
DB_CONFIG = {
    'host': 'localhost',      # Or your server IP
    'database': 'ocean_data', # Your database name
    'user': 'root',  # Your MySQL username
    'password': 'atharva123', # Your MySQL password
    'autocommit': True
}
# ===================================================

def execute_sql_query(sql_query):
    """Execute the SQL query and return results."""
    # Basic safety check - only allow SELECT statements
    sql_lower = sql_query.strip().lower()
    if not sql_lower.startswith('select'):
        return {"error": "Only SELECT queries are allowed for reading data."}
    
    connection = None
    try:
        # Establish database connection
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)  # Important: returns dicts
        
        # Execute the query
        cursor.execute(sql_query)
        results = cursor.fetchall()
        
        return {"success": True, "data": results}
    
    except Error as e:
        return {"error": f"MySQL Error: {str(e)}", "sql_query": sql_query}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "traceback": traceback.format_exc()}
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def main():
    """Main server loop - reads JSON-RPC requests from stdin"""
    print("Starting MySQL MCP Server...", file=sys.stderr)
    
    while True:
        try:
            # Read a line from stdin
            line = sys.stdin.readline().strip()
            if not line:
                break
                
            request = json.loads(line)
            
            if request.get("method") == "run_query":
                sql_query = request["params"]["sql_query"]
                result = execute_sql_query(sql_query)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id", 1),
                    "result": result
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id", 1),
                    "error": {"message": f"Unknown method: {request.get('method')}"}
                }
            
            # Write response to stdout
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            
        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"message": "Invalid JSON request"}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id", 1) if 'request' in locals() else None,
                "error": {"message": f"Server error: {str(e)}"}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()