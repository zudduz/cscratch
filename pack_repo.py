import os
import fnmatch
from datetime import datetime

# CONFIGURE OUTPUT DIRECTORY
OUTPUT_DIR = "repo_context"

# DEFAULT IGNORE LIST
ALWAYS_IGNORE = [
    ".git", ".idea", ".vscode", "__pycache__", "node_modules", 
    "venv", ".env", "dist", "build", "*.pyc", "*.lock", 
    "package-lock.json", "yarn.lock", "ai-reference", 
    OUTPUT_DIR,  # Ignore the output directory
    __file__
]

def load_gitignore(root_dir):
    ignore_patterns = []
    gitignore_path = os.path.join(root_dir, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ignore_patterns.append(line)
    return ignore_patterns

def should_ignore(path, root_dir, ignore_patterns):
    rel_path = os.path.relpath(path, root_dir)

    # Check default strict ignores
    for pattern in ALWAYS_IGNORE:
        if pattern in rel_path.split(os.sep):
            return True
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
            return True

    # Check .gitignore patterns
    for pattern in ignore_patterns:
        if pattern.endswith("/"): 
            pattern = pattern.rstrip("/")
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
            return True
            
    return False

def is_binary(file_path):
    try:
        with open(file_path, 'tr', encoding='utf-8') as check_file:
            check_file.read(1024)
            return False
    except:
        return True

def pack_repo():
    # --- Create the output directory ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"repo_context_{timestamp}.xml"
    OUTPUT_FILE = os.path.join(OUTPUT_DIR, output_filename)

    root_dir = os.getcwd()
    ignore_patterns = load_gitignore(root_dir)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("<repository_dump>\n")

        for dirpath, dirnames, filenames in os.walk(root_dir, topdown=True):
            dirnames[:] = [d for d in dirnames if not should_ignore(os.path.join(dirpath, d), root_dir, ignore_patterns)]
            
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                
                if should_ignore(file_path, root_dir, ignore_patterns):
                    continue
                
                if is_binary(file_path):
                    print(f"Skipping binary file: {filename}")
                    continue

                rel_path = os.path.relpath(file_path, root_dir)
                print(f"Packing: {rel_path}")
                
                try:
                    with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
                        content = f.read()
                    
                    out.write(f'<file path="{rel_path}">\n')
                    out.write(content)
                    out.write(f'\n</file>\n')
                    
                except Exception as e:
                    print(f"Error reading {rel_path}: {e}")
        
        out.write("</repository_dump>")

    print(f"\nDONE. Context packed into: {OUTPUT_FILE}")
    
    # Open the file in the editor
    try:
        os.system(f"code {OUTPUT_FILE}")
    except Exception as e:
        print(f"Could not open file in editor: {e}")

if __name__ == "__main__":
    pack_repo()