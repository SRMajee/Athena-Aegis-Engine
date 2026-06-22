import os

search_str = "ee1b4974-b48c-4f0a-8441-a33230a8b77e"
gemini_dir = r"C:\Users\User\.gemini"

for root, dirs, files in os.walk(gemini_dir):
    # Skip large conversation files to avoid slow searches
    if "conversations" in root or "brain" in root:
        continue
    for file in files:
        file_path = os.path.join(root, file)
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if search_str in content:
                    print(f"Found in: {file_path}")
        except Exception:
            pass
