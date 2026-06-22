import os

target = r"C:\Users\User\.gemini\config\projects"
for root, dirs, files in os.walk(target):
    for file in files:
        print(os.path.join(root, file))
