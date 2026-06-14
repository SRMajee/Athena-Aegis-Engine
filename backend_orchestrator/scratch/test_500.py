import subprocess
import time
import sys
import threading
import httpx

def log_reader(proc):
    for line in iter(proc.stdout.readline, ''):
        print(f"[SERVER LOG] {line.strip()}")

def main():
    print("Starting FastAPI app on port 8085...")
    proc = subprocess.Popen(
        f'"{sys.executable}" -u -m uvicorn server_fastapi:app --host 127.0.0.1 --port 8085',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    t = threading.Thread(target=log_reader, args=(proc,), daemon=True)
    t.start()
    
    # Wait for server to start
    time.sleep(4)
    
    print("Making request to http://127.0.0.1:8085/api/strategies...")
    try:
        res = httpx.get("http://127.0.0.1:8085/api/strategies", timeout=3.0)
        print(f"Response Status: {res.status_code}")
        print(f"Response Body: {res.text}")
    except Exception as e:
        print(f"Request failed: {e}")
        
    print("Terminating server...")
    proc.terminate()
    time.sleep(2)
    proc.kill()
    print("Done.")

if __name__ == "__main__":
    main()
