import logging
import json
import sys

class GoogleCloudFormatter(logging.Formatter):
    """
    Formats logs into JSON for Google Cloud Logging.
    Maps Python log levels to GCP 'severity'.
    """
    def format(self, record):
        # Map Python level to GCP severity
        severity_map = {
            'DEBUG': 'DEBUG',
            'INFO': 'INFO',
            'WARNING': 'WARNING',
            'ERROR': 'ERROR',
            'CRITICAL': 'CRITICAL'
        }
        
        # Build the structured payload
        json_log = {
            "severity": severity_map.get(record.levelname, 'DEFAULT'),
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": record.created,
            "logging.googleapis.com/sourceLocation": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName
            }
        }

        # Handle exceptions (stack traces)
        if record.exc_info:
            # Format the exception and append it to the message or a separate field
            text_trace = self.formatException(record.exc_info)
            json_log["message"] += f"\n{text_trace}"
            # GCP often looks for 'stack_trace' or 'exception' for UI grouping
            json_log["stack_trace"] = text_trace

        return json.dumps(json_log)

def setup_logging():
    """Configures the root logger to output JSON to stdout."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Create the JSON handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(GoogleCloudFormatter())
    root_logger.addHandler(handler)
    
    # Silence some noisy libraries if needed
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
