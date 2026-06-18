import json

path = r"C:\Users\User\.gemini\config\projects\SRMajee\Affinity-Core\project.json"
try:
    with open(path, "r", encoding="utf-8") as f:
        print(f.read())
except Exception as e:
    print(f"Error reading file: {e}")
