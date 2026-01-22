import os
import xml.etree.ElementTree as ET
import argparse

def unpack_repo(xml_file):
    """Unpacks the repository from an XML file."""
    if not os.path.exists(xml_file):
        print(f"Error: {xml_file} not found.")
        return

    tree = ET.parse(xml_file)
    root = tree.getroot()

    for file_elem in root.findall('file'):
        file_path = file_elem.get('path')
        content = file_elem.text

        if file_path and content is not None:
            try:
                # Ensure the directory exists
                dir_name = os.path.dirname(file_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)

                # Write the file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Updated: {file_path}")

            except Exception as e:
                print(f"Error writing {file_path}: {e}")

    print("\nDONE. All files updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unpack a repository from a single XML file.")
    parser.add_argument("xml_file", help="The XML file to unpack (e.g., repo_context.xml)")
    args = parser.parse_args()

    unpack_repo(args.xml_file)
