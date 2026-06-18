import os
import json

target = r"C:\Users\User\.gemini\config\projects"
search_str = "ee1b4974-b48c-4f0a-8441-a33230a8b77e"
for file in os.listdir(target):
    if file.endswith(".json"):
        path = os.path.join(target, file)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                if search_str in content:
                    print(f"Found in: {path}")
                    # Parse and print keys or whole JSON if it's small
                    try:
                        data = json.loads(content)
                        print(json.dumps(data, indent=2))
                    except Exception as je:
                        print(f"Error parsing JSON: {je}")
        except Exception as e:
            print(f"Error reading {file}: {e}")
