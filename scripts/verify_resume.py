import json

from research_domain.controllers import ResearcherController

ctrl = ResearcherController()
researchers = ctrl.get_all()

for r in researchers:
    # Print search criteria to debug
    # print(f"Checking {r.name}...")

    # Try multiple ways to match Lattes ID if unknown where it is exactly
    match = False
    if r.name == "Paulo Sergio dos Santos Junior":
        match = True

    if match:
        print(f"Researcher: {r.name}")
        print(f"Resume: {r.resume[:150]}..." if r.resume else "Resume: None")
        # Verify it can be serialized
        try:
            print(f"Serialized Resume length: {len(r.to_dict().get('resume', ''))}")
        except Exception as e:
            print(f"Serialization error: {e}")
