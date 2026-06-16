import os
import shutil
from pathlib import Path

def reorganize():
    workspace_root = Path(__file__).resolve().parent.parent.parent
    data_dir = workspace_root / "data"
    
    if not data_dir.exists():
        print(f"Data directory not found at {data_dir}")
        return
        
    for symbol_dir in data_dir.iterdir():
        if not symbol_dir.is_dir() or symbol_dir.name == "temp":
            continue
        
        print(f"Checking files in {symbol_dir.name}...")
        for file in list(symbol_dir.iterdir()):
            if file.is_file() and file.suffix.lower() == ".parquet":
                name = file.stem
                # check if it is a 8-digit date like 20100104
                if len(name) == 8 and name.isdigit():
                    year = name[:4]
                    dest_dir = symbol_dir / year
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    
                    dest_file = dest_dir / file.name
                    print(f"Moving {file.name} to {symbol_dir.name}/{year}/{file.name}")
                    shutil.move(str(file), str(dest_file))

if __name__ == "__main__":
    reorganize()
