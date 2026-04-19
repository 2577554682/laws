# check_patterns.py
import json

with open("resources/crime_patterns.json", "r", encoding="utf-8") as f:
    patterns = json.load(f)

print(f"当前共有 {len(patterns)} 个罪名：")
for i, crime in enumerate(list(patterns.keys())[:20]):
    print(f"{i+1}. {crime}")