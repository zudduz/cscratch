import os
import sys

TARGET_DIR = "cartridges/foster_protocol"

def check_syntax(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        compile(source, file_path, "exec")
        print(f"✅ PASS: {os.path.basename(file_path)}")
        return True
    except SyntaxError as e:
        print(f"❌ FAIL: {os.path.basename(file_path)}")
        print(f"   Line {e.lineno}: {e.text.strip() if e.text else '?'}")
        print(f"   Error: {e.msg}")
        return False
    except Exception as e:
        print(f"⚠️ ERROR: Could not read {file_path} - {e}")
        return False

def main():
    if not os.path.exists(TARGET_DIR):
        print(f"Directory not found: {TARGET_DIR}")
        return

    files = [f for f in os.listdir(TARGET_DIR) if f.endswith(".py")]
    if not files:
        print("No Python files found.")
        return

    print(f"--- SCANNING {len(files)} FILES IN {TARGET_DIR} ---")
    all_pass = True
    for file in files:
        if not check_syntax(os.path.join(TARGET_DIR, file)):
            all_pass = False

    print("-" * 30)
    if all_pass:
        print("🎉 ALL SYSTEMS NOMINAL. READY FOR DEPLOY.")
        sys.exit(0)
    else:
        print("🔥 CRITICAL SYNTAX FAILURES DETECTED.")
        sys.exit(1)

if __name__ == "__main__":
    main()