import json
import os
from datetime import datetime, timezone
from typing import Any

from loguru import logger


class ResearchGroupMembershipGraphsManifestGenerator:
    """
    Scans the research_group_membership_graphs directory and produces a
    manifest/index JSON listing every group graph with its key stats.
    """

    GRAPHS_DIR = "research_group_membership_graphs"

    def generate(self, output_dir: str, output_path: str) -> dict[str, Any]:
        graphs_dir = os.path.join(output_dir, self.GRAPHS_DIR)
        logger.info("Scanning {} for group graphs", graphs_dir)

        if not os.path.isdir(graphs_dir):
            raise FileNotFoundError(f"Graphs directory not found: {graphs_dir}")

        entries = []
        for filename in sorted(os.listdir(graphs_dir)):
            if not filename.endswith(".json"):
                continue

            filepath = os.path.join(graphs_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as exc:
                logger.warning("Skipping {}: {}", filename, exc)
                continue

            scope = data.get("metadata", {}).get("scope", {}).get("research_group", {})
            stats = data.get("graph_stats", {})

            entries.append(
                {
                    "id": scope.get("id"),
                    "name": scope.get("name"),
                    "short_name": scope.get("short_name"),
                    "member_count": scope.get("member_count"),
                    "expanded_node_count": scope.get("expanded_node_count"),
                    "advisorship_neighbor_count": scope.get(
                        "advisorship_neighbor_count"
                    ),
                    "nodes": stats.get("nodes"),
                    "edges": stats.get("edges"),
                    "connected_components": stats.get("connected_components"),
                    "classification_distribution": stats.get(
                        "classification_distribution"
                    ),
                    "relation_event_totals": stats.get("relation_event_totals"),
                    "file": os.path.join(self.GRAPHS_DIR, filename),
                }
            )

        entries.sort(key=lambda e: (e["id"] is None, e["id"]))

        manifest = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_groups": len(entries),
                "total_nodes": sum(e["nodes"] or 0 for e in entries),
                "total_edges": sum(e["edges"] or 0 for e in entries),
                "graphs_directory": self.GRAPHS_DIR,
            },
            "groups": entries,
        }

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        logger.info(
            "Manifest generated: {} groups, {} total nodes, {} total edges → {}",
            len(entries),
            manifest["metadata"]["total_nodes"],
            manifest["metadata"]["total_edges"],
            output_path,
        )
        return manifest
