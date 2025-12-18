
from mcp.server.fastmcp import FastMCP
from google.cloud import logging
import inspect
import importlib
import pydoc
import os

# Initialize the server
mcp = FastMCP("OpsManager")

@mcp.tool()
def read_cloud_logs(limit: int = 20) -> str:
    """
    Fetches recent application logs for the Cloud Run service defined by the SERVICE_NAME env var.
    Use this when the application crashes or returns 500 errors to see the stack trace.
    """
    service_name = os.environ.get("SERVICE_NAME")
    if not service_name:
        return "Error: SERVICE_NAME environment variable is not set. Please configure it in .idx/mcp.json."

    try:
        logging_client = logging.Client()
        
        # Filter to get logs for the specific service
        filter_str = f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service_name}"'
        
        entries = logging_client.list_entries(filter_=filter_str, order_by=logging.DESCENDING, page_size=limit)
        
        logs = []
        for entry in entries:
            # Reverse to show oldest first for readability
            timestamp = entry.timestamp.strftime("%H:%M:%S")
            payload = entry.payload
            logs.append(f"[{timestamp}] {payload}")
            
        if not logs:
            return f"No logs found for service '{service_name}'."

        return "\n".join(logs[::-1])
    except Exception as e:
        return f"Error fetching logs: {str(e)}. (Is the gcloud user authenticated?)"

@mcp.tool()
def inspect_library_source(import_path: str) -> str:
    """
    Reads the ACTUAL source code of a Python library function or class.
    Use this to check arguments, default values, and logic.
    Example: inspect_library_source("langgraph.graph.StateGraph")
    """
    try:
        parts = import_path.split('.')
        module_name = parts[0]
        
        module = importlib.import_module(module_name)
        
        obj = module
        for part in parts[1:]:
            obj = getattr(obj, part)
            
        source = inspect.getsource(obj)
        file_path = inspect.getfile(obj)
        
        return f"--- Source of {import_path} ({file_path}) ---\n{source}"
    except Exception as e:
        return f"Could not read source for {import_path}: {str(e)}"

@mcp.tool()
def search_pydoc(keyword: str) -> str:
    """
    Searches the installed Python documentation for a keyword.
    Use this to find the correct method names or class descriptions.
    """
    try:
        return pydoc.render_doc(keyword, renderer=pydoc.plaintext)
    except Exception as e:
        return f"Error searching docs: {str(e)}"

if __name__ == "__main__":
    mcp.run()
