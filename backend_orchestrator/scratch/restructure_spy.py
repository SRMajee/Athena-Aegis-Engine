import os
import shutil
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent.parent
    spy_dir = root / "data" / "SPY"
    old_2010_dir = spy_dir / "2010"
    
    if not old_2010_dir.exists():
        print("data/SPY/2010 directory does not exist.")
        return
        
    print("Restructuring SPY 2010 files to options-data layout...")
    
    # We will create a temp directory first, then move files, then replace old_2010_dir
    temp_dir = root / "data" / "SPY" / "2010_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    for f in old_2010_dir.iterdir():
        if f.is_file() and f.suffix == ".parquet":
            stem = f.stem # e.g. 20100104
            if len(stem) == 8 and stem.isdigit():
                year = stem[0:4]
                month = stem[4:6]
                day = stem[6:8]
                new_name = f"{year}-{month}-{day}.parquet"
                
                target_month_dir = temp_dir / month
                target_month_dir.mkdir(parents=True, exist_ok=True)
                
                shutil.copy2(f, target_month_dir / new_name)
                
    # Now verify all files are copied, delete old_2010_dir, and rename temp_dir to 2010
    old_files_count = len(list(old_2010_dir.glob("*.parquet")))
    new_files_count = len(list(temp_dir.rglob("*.parquet")))
    
    print(f"Old file count: {old_files_count}, New file count: {new_files_count}")
    
    if old_files_count == new_files_count:
        shutil.rmtree(old_2010_dir)
        temp_dir.rename(old_2010_dir)
        print("Successfully restructered SPY 2010 directory!")
    else:
        print("Error: File count mismatch. Did not complete restructuring.")

if __name__ == "__main__":
    main()
