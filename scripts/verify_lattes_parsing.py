import json
import os
import sys
from pprint import pprint

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))
# Check where we run from. Assuming running from horizon_etl root.
sys.path.append(os.getcwd())

from src.adapters.sources.lattes_parser import LattesParser


def verify_parsing():
    file_path = "data/lattes/00_Paulo-Sergio-dos-Santos-Junior_8400407353673370.json"
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        # Try absolute path just in case
        file_path = "/home/paulossjunior/projects/horizon_project/horizon_dashboard/src/data/lattes/00_Paulo-Sergio-dos-Santos-Junior_8400407353673370.json"
        if not os.path.exists(file_path):
            print(f"File definitely not found at {file_path}")
            return

    print(f"Parsing {file_path}...")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    parser = LattesParser()

    print("\n--- Research Projects ---")
    pesq = parser.parse_research_projects(data)
    for p in pesq[:3]:  # Show first 3
        pprint(p)
        print("-" * 20)
    print(f"Total Research: {len(pesq)}")

    print("\n--- Extension Projects ---")
    ext = parser.parse_extension_projects(data)
    for p in ext[:3]:
        pprint(p)
        print("-" * 20)
    print(f"Total Extension: {len(ext)}")

    print("\n--- Development Projects ---")
    dev = parser.parse_development_projects(data)
    for p in dev[:3]:
        pprint(p)
        print("-" * 20)
    print(f"Total Development: {len(dev)}")


if __name__ == "__main__":
    verify_parsing()
