import argparse
import os
import vertexai
from vertexai.generative_models import GenerativeModel

# Configuration (Matches your project)
PROJECT_ID = "sandbox-456821"
LOCATION = "us-central1"
# We use Flash for counting as the tokenizer is generally consistent across the Gemini family
MODEL_ID = "gemini-2.5-flash" 

def count_file_tokens(file_path):
    try:
        # Initialize Vertex AI
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel(MODEL_ID)

        # Read File
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Count
        response = model.count_tokens(content)
        count = response.total_tokens
        
        print(f"📄 File:   {file_path}")
        print(f"🔢 Tokens: {count}")
        
        # Cache Check
        if count >= 1500:
            print("✅ Status: Cacheable (>= 1500)")
        else:
            diff = 1500 - count
            print(f"⚠️ Status: Too Short (Need {diff} more for implicit caching)")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count tokens for Gemini Context Caching")
    parser.add_argument("file", help="Path to the text/markdown file to analyze")
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"File not found: {args.file}")
    else:
        count_file_tokens(args.file)