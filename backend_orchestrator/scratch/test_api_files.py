import httpx

def main():
    url = "http://localhost:8085/api/files"
    try:
        resp = httpx.get(url, timeout=10.0)
        print(f"Status: {resp.status_code}")
        files = resp.json()
        print(f"Total files/segments returned: {len(files)}")
        for f in files:
            if f.get("type") == "segment":
                print(f"Segment: name={f.get('name')}, days={f.get('number_of_days')}, start={f.get('date_start')}, end={f.get('date_end')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
