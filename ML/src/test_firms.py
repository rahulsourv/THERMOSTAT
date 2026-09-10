import os
import requests
from dotenv import load_dotenv

load_dotenv()

MAP_KEY = os.getenv("FIRMS_MAP_KEY")

if not MAP_KEY:
    raise ValueError("FIRMS_MAP_KEY not found in .env")

# India bounding box:
# west, south, east, north
area = "world"

url = (
    f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
    f"{MAP_KEY}/VIIRS_SNPP_NRT/{area}/1"
)

response = requests.get(url)

print("Status:", response.status_code)

if response.ok:
    print(response.text[:3000])
else:
    print(response.text)