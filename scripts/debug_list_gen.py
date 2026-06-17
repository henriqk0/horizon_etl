import os

from src.core.logic.lattes_generators import LattesListGenerator

gen = LattesListGenerator()
path = os.path.abspath("lattes.list")
print(f"Generating to: {path}")
gen.generate_from_db(path, [{"name": "Test", "lattes_id": "123"}])
if os.path.exists(path):
    print("Success: File exists")
    with open(path, "r") as f:
        print(f"Content: {f.read()}")
else:
    print("Failure: File does not exist")
