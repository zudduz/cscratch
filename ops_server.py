from mcp.server.fastmcp import FastMCP
from google.cloud import logging
import inspect
import importlib
import pydoc
import sys

# Initialize the server
mcp = FastMCP("OpsManager")

@mcp.tool()
def read_cloud_logs(service_name: str, limit: int = 20) -> str:
    """
    Fetches the recent application logs for a specific Cloud Run service.
    Use this when the application crashes or returns 500 errors to see the stack trace.
    """
    try:
        logging_client = logging.Client()
        logger = logging_client.logger("cloud-run-stdout") # Adjust based on your log sink
        
        # Simple filter to get logs for your specific service
        filter_str = f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service_name}"'
        
        entries = logging_client.list_entries(filter_=filter_str, order_by=logging.DESCENDING, page_size=limit)
        
        logs = []
        for entry in entries:
            # We reverse to show oldest first in the snippet for readability
            timestamp = entry.timestamp.strftime("%H:%M:%S")
            payload = entry.payload
            logs.append(f"[{timestamp}] {payload}")
            
        return "\n".join(logs[::-1])
    except Exception as e:
        return f"Error fetching logs: {str(e)}. (Check your GCP credentials?)"

@mcp.tool()
def inspect_library_source(import_path: str) -> str:
    """
    Reads the ACTUAL source code of a Python library function or class.
    Use this to check arguments, default values, and logic.
    Example: inspect_library_source("langgraph.graph.StateGraph")
    """
    try:
        # Split module and object (e.g., 'json.dumps' -> module 'json', object 'dumps')
        parts = import_path.split('.')
        module_name = parts[0]
        
        # Dynamically import the module
        module = importlib.import_module(module_name)
        
        # Traverse to get the specific object
        obj = module
        for part in parts[1:]:
            obj = getattr(obj, part)
            
        # Get the source code
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
        # Uses Python's built-in help system helper
        return pydoc.render_doc(keyword, renderer=pydoc.plaintext)
    except Exception as e:
        return f"Error searching docs: {str(e)}"

if __name__ == "__main__":
    mcp.run()