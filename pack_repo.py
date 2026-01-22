import os
import sys
import codecs
import subprocess
import argparse

OUTPUT_FILENAME = "repo_context.xml"

def load_gitignore(root_dir):
    """Loads ignore patterns from .gitignore and .editorexclude files."""
    ignore_patterns = set()
    for filename in [".gitignore", ".editorexclude"]:
        gitignore_path = os.path.join(root_dir, filename)
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if line.endswith('/'):
                            line = line[:-1]
                        ignore_patterns.add(line)
    ignore_patterns.add(".git")
    ignore_patterns.add(".DS_Store")
    ignore_patterns.add(OUTPUT_FILENAME)
    return ignore_patterns

def should_ignore(path, root_dir, ignore_patterns):
    """Checks if a file or directory should be ignored."""
    rel_path = os.path.relpath(path, root_dir)
    rel_path_parts = rel_path.replace('\\', '/').split('/')
    
    for pattern in ignore_patterns:
        pattern_parts = pattern.split('/')
        if len(rel_path_parts) >= len(pattern_parts):
            if rel_path_parts[:len(pattern_parts)] == pattern_parts:
                return True
    return False

def is_binary(file_path):
    """Heuristic to check if a file is binary."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            return b'\x00' in chunk
    except:
        return True

def pack_repo(target_dir=None):
    """Packs the repository into an XML file, optionally focusing on a specific directory."""
    OUTPUT_FILE = OUTPUT_FILENAME

    project_root = os.getcwd()
    start_dir = os.path.join(project_root, target_dir) if target_dir else project_root
    
    ignore_patterns = load_gitignore(project_root)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("<repository_dump>\n")

        for dirpath, dirnames, filenames in os.walk(start_dir, topdown=True):
            dirnames[:] = [d for d in dirnames if not should_ignore(os.path.join(dirpath, d), project_root, ignore_patterns)]

            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                
                if should_ignore(file_path, project_root, ignore_patterns):
                    continue
                
                if is_binary(file_path):
                    print(f"Skipping binary file: {filename}")
                    continue

                rel_path = os.path.relpath(file_path, project_root)
                print(f"Packing: {rel_path}")
                
                try:
                    with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
                        content = f.read()
                    
                    out.write(f'<file path="{rel_path}">\n')
                    out.write(f"<![CDATA[{content}]]>")
                    out.write(f'\n</file>\n')
                    
                except Exception as e:
                    print(f"Error reading {rel_path}: {e}")
        
        out.write("</repository_dump>")

    print(f"\nDONE. Context packed into: {OUTPUT_FILE}")
    return OUTPUT_FILE

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pack a repository into a single XML file.")
    parser.add_argument("directory", nargs='?', default=None, help="Optional: The specific directory to pack (relative to the project root).")
    args = parser.parse_args()

    output_file = pack_repo(target_dir=args.directory)
    
    try:
        subprocess.run(["code", output_file], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"Could not open {output_file} in VS Code. Please open it manually.")
