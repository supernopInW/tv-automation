import os
import json

base_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(base_dir)
villages_dir = os.path.join(project_dir, "data", "villages")
all_villages = {}

if os.path.exists(villages_dir):
    for fname in os.listdir(villages_dir):
        if fname.endswith(".json"):
            tcode = fname[:-5]
            fpath = os.path.join(villages_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data:
                        all_villages[tcode] = data
            except Exception as e:
                pass

out_path = os.path.join(project_dir, "data", "villages_all.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(all_villages, f, ensure_ascii=False, separators=(',', ':'))

print(f"Total tambons merged: {len(all_villages)}")
print(f"File size: {os.path.getsize(out_path) / (1024*1024):.2f} MB")
