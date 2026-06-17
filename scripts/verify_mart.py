import json
import os


def verify_mart(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or len(data) == 0:
        print("Error: Mart JSON should be a list containing at least one object.")
        return False

    mart = data[0]
    required_keys = ["projects", "global_stats", "rankings", "generated_at"]
    for key in required_keys:
        if key not in mart:
            print(f"Error: Missing key '{key}' in mart.")
            return False

    stats = mart["global_stats"]
    required_stats = [
        "total_projects",
        "total_advisorships",
        "total_active_advisorships",
        "total_monthly_investment",
        "program_distribution",
        "investment_per_program",
        "participation_ratio",
        "volunteer_percentage",
        "volunteer_count",
    ]
    for stat in required_stats:
        if stat not in stats:
            print(f"Error: Missing stat '{stat}' in global_stats.")
            return False

    # Value checks
    if stats["participation_ratio"] <= 0:
        print(f"Warning: participation_ratio is {stats['participation_ratio']}")

    if not (0 <= stats["volunteer_percentage"] <= 100):
        print(
            f"Error: volunteer_percentage {stats['volunteer_percentage']} out of range."
        )
        return False

    rankings = mart["rankings"]
    required_rankings = ["top_supervisors", "top_projects_by_investment"]
    for rank in required_rankings:
        if rank not in rankings:
            print(f"Error: Missing ranking '{rank}' in rankings.")
            return False

    print("Success: Advisorship Analytics Mart verified successfully.")
    print(f"Total Projects: {stats['total_projects']}")
    print(f"Total Advisorships: {stats['total_advisorships']}")
    print(f"Volunteer Percentage: {stats['volunteer_percentage']}%")
    print(f"Participation Ratio: {stats['participation_ratio']}")
    return True


if __name__ == "__main__":
    verify_mart("data/exports/advisorship_analytics.json")
