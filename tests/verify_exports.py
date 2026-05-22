import json


def verify_exports():
    # 1. Load Researchers Export
    with open("data/exports/researchers_canonical.json", "r") as f:
        researchers = json.load(f)

    daniel = next(
        (r for r in researchers if "Daniel Cruz Cavalieri" in r["name"]), None
    )

    if not daniel:
        print("ERROR: Daniel not found in researchers_canonical.json")
        return

    print(f"Found Daniel: {daniel['name']}")

    # Check if advisorships are directly in researcher object
    advs = daniel.get("advisorships", [])
    print(f"Advisorships in 'researchers_canonical.json': {len(advs)}")

    # 2. Load Advisorships Export (if separate)
    try:
        with open("data/exports/advisorships_canonical.json", "r") as f:
            all_advs = json.load(f)

        # Count advisorships where Daniel is supervisor
        # Need to check the structure. Usually it's a list of advisorship objects.
        # Or maybe check the parent key?

        # Let's inspect the first item to see structure
        if all_advs:
            print(f"Sample Advisorship Item Keys: {all_advs[0].keys()}")

        # Assuming structure based on previous logs (parent projects with advisorships?)
        # "Filtered export: 161 parent projects with advisorships"
        # It seems `advisorships_canonical.json` might be grouped by project or just a flat list.
        # Let's count items where supervisor name matches Daniel if flat, or check nested if grouped.

        daniel_adv_count = 0
        for item in all_advs:
            # Check if this item IS an advisorship
            if item.get("supervisor_name") == "Daniel Cruz Cavalieri":  # if flattened
                daniel_adv_count += 1
            # Check nested
            elif "advisorships" in item:
                for sub in item["advisorships"]:
                    if "Daniel" in sub.get("supervisor_name", ""):  # Loose match
                        daniel_adv_count += 1

        print(
            f"Advisorships found in 'advisorships_canonical.json': {daniel_adv_count}"
        )

    except FileNotFoundError:
        print("advisorships_canonical.json not found.")


if __name__ == "__main__":
    verify_exports()
