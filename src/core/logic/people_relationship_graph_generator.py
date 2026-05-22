import json
import os
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Iterable, Optional

import networkx as nx
from loguru import logger
from networkx.readwrite import json_graph

RELATION_DESCRIPTIONS = {
    "initiative": "People who appear together in the same initiative team.",
    "research_group": "People who belong to the same research group.",
    "advisorship": "Supervisor and student connected by an advisorship.",
}

CLASSIFICATION_GRAPH_EXPORTS: tuple[tuple[Optional[str], str], ...] = (
    ("student", "students_relationship_graph.json"),
    ("researcher", "researchers_only_relationship_graph.json"),
    ("outside_ifes", "outside_ifes_relationship_graph.json"),
    (None, "null_researchers_relationship_graph.json"),
)

RESEARCH_GROUP_GRAPH_DIRECTORY = "research_group_relationship_graphs"
RESEARCH_GROUP_GRAPH_MANIFEST = "research_group_relationship_graphs_manifest.json"
RESEARCH_GROUP_MEMBERSHIP_GRAPH_DIRECTORY = "research_group_membership_graphs"


class PeopleRelationshipGraphGenerator:
    def generate(
        self,
        researchers_path: str,
        initiatives_path: str,
        research_groups_path: str,
        advisorships_path: str,
        output_path: str,
    ) -> dict[str, Any]:
        logger.info("Generating People Relationship Graph to {}", output_path)

        sources, graph, _research_groups = self._build_graph_from_paths(
            researchers_path=researchers_path,
            initiatives_path=initiatives_path,
            research_groups_path=research_groups_path,
            advisorships_path=advisorships_path,
        )
        result = self._serialize_graph_result(graph, sources=sources)
        self._write_json(output_path, result)

        logger.info(
            "People Relationship Graph successfully generated at {} with {} nodes and {} edges",
            output_path,
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )
        return result

    def generate_all(
        self,
        researchers_path: str,
        initiatives_path: str,
        research_groups_path: str,
        advisorships_path: str,
        output_dir: str,
    ) -> dict[str, Any]:
        logger.info(
            "Generating People Relationship Graph bundle into directory {}", output_dir
        )

        sources, graph, research_groups = self._build_graph_from_paths(
            researchers_path=researchers_path,
            initiatives_path=initiatives_path,
            research_groups_path=research_groups_path,
            advisorships_path=advisorships_path,
        )

        full_output_path = os.path.join(output_dir, "people_relationship_graph.json")
        full_result = self._serialize_graph_result(graph, sources=sources)
        self._write_json(full_output_path, full_result)

        classification_exports = []
        for classification, filename in CLASSIFICATION_GRAPH_EXPORTS:
            filtered_graph = self._build_classification_subgraph(graph, classification)
            output_path = os.path.join(output_dir, filename)
            result = self._serialize_graph_result(
                filtered_graph,
                sources=sources,
                scope={
                    "type": "classification",
                    "classification": (
                        "null" if classification is None else classification
                    ),
                },
            )
            self._write_json(output_path, result)
            classification_exports.append(
                {
                    "classification": (
                        "null" if classification is None else classification
                    ),
                    "path": output_path,
                    "nodes": result["graph_stats"]["nodes"],
                    "edges": result["graph_stats"]["edges"],
                }
            )

        research_group_manifest = self._export_research_group_graphs(
            graph=graph,
            research_groups=research_groups,
            sources=sources,
            output_dir=output_dir,
        )

        membership_alias = os.path.join(
            output_dir, RESEARCH_GROUP_MEMBERSHIP_GRAPH_DIRECTORY
        )
        if os.path.islink(membership_alias):
            os.unlink(membership_alias)
        if not os.path.exists(membership_alias):
            os.symlink(RESEARCH_GROUP_GRAPH_DIRECTORY, membership_alias)

        logger.info(
            "People Relationship Graph bundle generated with {} classification graphs and {} research-group graphs",
            len(classification_exports),
            len(research_group_manifest["graphs"]),
        )

        return {
            "full_graph_path": full_output_path,
            "classification_exports": classification_exports,
            "research_group_exports": research_group_manifest,
        }

    def _build_graph_from_paths(
        self,
        researchers_path: str,
        initiatives_path: str,
        research_groups_path: str,
        advisorships_path: str,
    ) -> tuple[dict[str, str], nx.Graph, list[dict[str, Any]]]:
        researchers = self._load_json(researchers_path)
        initiatives = self._load_json(initiatives_path)
        research_groups = self._load_json(research_groups_path)
        advisorship_projects = self._load_json(advisorships_path)

        graph = self._build_graph(
            researchers=researchers,
            initiatives=initiatives,
            research_groups=research_groups,
            advisorship_projects=advisorship_projects,
        )

        return (
            {
                "researchers": researchers_path,
                "initiatives": initiatives_path,
                "research_groups": research_groups_path,
                "advisorships": advisorships_path,
            },
            graph,
            research_groups,
        )

    def _build_graph(
        self,
        researchers: list[dict[str, Any]],
        initiatives: list[dict[str, Any]],
        research_groups: list[dict[str, Any]],
        advisorship_projects: list[dict[str, Any]],
    ) -> nx.Graph:
        graph = nx.Graph()

        self._add_researcher_nodes(graph, researchers)
        self._add_initiative_relationships(graph, initiatives)
        self._add_research_group_relationships(graph, research_groups)
        self._add_advisorship_relationships(graph, advisorship_projects)
        self._finalize_graph(graph)

        return graph

    @staticmethod
    def _load_json(path: str) -> list[dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
        return payload if isinstance(payload, list) else []

    def _serialize_graph_result(
        self,
        graph: nx.Graph,
        sources: dict[str, str],
        scope: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        graph_payload = json_graph.node_link_data(graph, edges="edges")
        return {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": sources,
                "scope": scope or {"type": "full"},
                "weight_definition": (
                    "Each edge weight equals the total number of relationship "
                    "evidences between two people. Every shared initiative, shared "
                    "research group, and advisorship adds 1 to the edge weight."
                ),
                "relation_types": RELATION_DESCRIPTIONS,
            },
            "graph_stats": self._build_graph_stats(graph),
            "graph": graph_payload,
        }

    def _write_json(self, output_path: str, payload: dict[str, Any]) -> None:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, ensure_ascii=False, indent=4)

    def _build_classification_subgraph(
        self, graph: nx.Graph, classification: Optional[str]
    ) -> nx.Graph:
        selected_node_ids = [
            node_id
            for node_id, attrs in graph.nodes(data=True)
            if attrs.get("classification") == classification
        ]
        subgraph = graph.subgraph(selected_node_ids).copy()
        self._finalize_graph(subgraph)
        return subgraph

    def _export_research_group_graphs(
        self,
        graph: nx.Graph,
        research_groups: list[dict[str, Any]],
        sources: dict[str, str],
        output_dir: str,
    ) -> dict[str, Any]:
        graphs_output_dir = os.path.join(output_dir, RESEARCH_GROUP_GRAPH_DIRECTORY)
        manifest_graphs = []

        for group in research_groups:
            group_id = group.get("id")
            if group_id is None:
                continue

            participants = self._unique_people(
                (
                    member.get("id"),
                    member.get("name"),
                )
                for member in (group.get("members") or [])
            )
            member_node_ids = {
                person_id
                for person_id in sorted(participants.keys())
                if graph.has_node(person_id)
            }
            advisorship_neighbor_ids = self._find_advisorship_neighbors(
                graph=graph,
                seed_node_ids=member_node_ids,
            )
            node_ids = sorted(member_node_ids | advisorship_neighbor_ids)

            subgraph = graph.subgraph(node_ids).copy()
            self._annotate_research_group_subgraph_nodes(
                graph=subgraph,
                member_node_ids=member_node_ids,
                advisorship_neighbor_ids=advisorship_neighbor_ids,
            )
            self._finalize_graph(subgraph)

            output_path = os.path.join(
                graphs_output_dir,
                f"research_group_{group_id}_relationship_graph.json",
            )
            result = self._serialize_graph_result(
                subgraph,
                sources=sources,
                scope={
                    "type": "research_group",
                    "research_group": {
                        "id": group_id,
                        "name": group.get("name"),
                        "short_name": group.get("short_name"),
                        "member_count": len(member_node_ids),
                        "expanded_node_count": len(node_ids),
                        "advisorship_neighbor_count": len(
                            advisorship_neighbor_ids - member_node_ids
                        ),
                    },
                },
            )
            self._write_json(output_path, result)

            manifest_graphs.append(
                {
                    "id": group_id,
                    "name": group.get("name"),
                    "short_name": group.get("short_name"),
                    "member_count": len(member_node_ids),
                    "expanded_node_count": len(node_ids),
                    "advisorship_neighbor_count": len(
                        advisorship_neighbor_ids - member_node_ids
                    ),
                    "nodes": result["graph_stats"]["nodes"],
                    "edges": result["graph_stats"]["edges"],
                    "path": os.path.relpath(output_path, output_dir),
                }
            )

        manifest_payload = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "scope": {"type": "research_group_manifest"},
                "graphs_directory": RESEARCH_GROUP_GRAPH_DIRECTORY,
            },
            "graphs": manifest_graphs,
        }
        manifest_path = os.path.join(output_dir, RESEARCH_GROUP_GRAPH_MANIFEST)
        self._write_json(manifest_path, manifest_payload)

        return {
            "manifest_path": manifest_path,
            "graphs_directory": graphs_output_dir,
            "graphs": manifest_graphs,
        }

    def _find_advisorship_neighbors(
        self, graph: nx.Graph, seed_node_ids: set[int]
    ) -> set[int]:
        neighbor_ids: set[int] = set()
        for source_id, target_id, attrs in graph.edges(data=True):
            if attrs.get("advisorship_count", 0) <= 0:
                continue
            if source_id in seed_node_ids:
                neighbor_ids.add(target_id)
            if target_id in seed_node_ids:
                neighbor_ids.add(source_id)
        return neighbor_ids

    def _annotate_research_group_subgraph_nodes(
        self,
        graph: nx.Graph,
        member_node_ids: set[int],
        advisorship_neighbor_ids: set[int],
    ) -> None:
        for node_id, attrs in graph.nodes(data=True):
            attrs["is_group_member"] = node_id in member_node_ids
            attrs["is_advisorship_neighbor"] = (
                node_id in advisorship_neighbor_ids and node_id not in member_node_ids
            )

    def _add_researcher_nodes(
        self, graph: nx.Graph, researchers: list[dict[str, Any]]
    ) -> None:
        for researcher in researchers:
            person_id = self._normalize_person_id(researcher.get("id"))
            if person_id is None:
                continue
            graph.add_node(
                person_id,
                name=researcher.get("name"),
                classification=researcher.get("classification"),
                classification_confidence=researcher.get("classification_confidence"),
                was_student=bool(researcher.get("was_student")),
                was_staff=bool(researcher.get("was_staff")),
                campus_name=self._extract_campus_name(researcher.get("campus")),
            )

    def _add_initiative_relationships(
        self,
        graph: nx.Graph,
        initiatives: list[dict[str, Any]],
    ) -> None:
        for initiative in initiatives:
            members = initiative.get("team") or []
            participants = self._unique_people(
                (
                    member.get("person_id"),
                    member.get("person_name"),
                )
                for member in members
            )
            for person_id, person_name in participants.values():
                self._ensure_person_node(graph, person_id, person_name)

            for source_id, target_id in combinations(sorted(participants.keys()), 2):
                self._increment_edge(graph, source_id, target_id, "initiative")

    def _add_research_group_relationships(
        self,
        graph: nx.Graph,
        research_groups: list[dict[str, Any]],
    ) -> None:
        for group in research_groups:
            members = group.get("members") or []
            participants = self._unique_people(
                (
                    member.get("id"),
                    member.get("name"),
                )
                for member in members
            )
            for person_id, person_name in participants.values():
                self._ensure_person_node(graph, person_id, person_name)

            for source_id, target_id in combinations(sorted(participants.keys()), 2):
                self._increment_edge(graph, source_id, target_id, "research_group")

    def _add_advisorship_relationships(
        self,
        graph: nx.Graph,
        advisorship_projects: list[dict[str, Any]],
    ) -> None:
        for project in advisorship_projects:
            for advisorship in project.get("advisorships") or []:
                supervisor_id = self._normalize_person_id(
                    advisorship.get("supervisor_id")
                )
                person_id = self._normalize_person_id(advisorship.get("person_id"))
                if (
                    supervisor_id is None
                    or person_id is None
                    or supervisor_id == person_id
                ):
                    continue

                self._ensure_person_node(
                    graph,
                    supervisor_id,
                    advisorship.get("supervisor_name"),
                )
                self._ensure_person_node(
                    graph,
                    person_id,
                    advisorship.get("person_name"),
                )
                self._increment_edge(graph, supervisor_id, person_id, "advisorship")

    def _finalize_graph(self, graph: nx.Graph) -> None:
        weighted_degrees = dict(graph.degree(weight="weight"))
        plain_degrees = dict(graph.degree())

        for node_id, attrs in graph.nodes(data=True):
            attrs["degree"] = plain_degrees.get(node_id, 0)
            attrs["weighted_degree"] = weighted_degrees.get(node_id, 0)
            if attrs.get("classification") is None:
                attrs["classification"] = None

        for _source_id, _target_id, attrs in graph.edges(data=True):
            attrs["relation_types"] = [
                relation_type
                for relation_type in ("initiative", "research_group", "advisorship")
                if attrs.get(f"{relation_type}_count", 0) > 0
            ]

    def _build_graph_stats(self, graph: nx.Graph) -> dict[str, Any]:
        components = list(nx.connected_components(graph))
        isolated_nodes = list(nx.isolates(graph))
        weighted_degrees = dict(graph.degree(weight="weight"))
        relation_event_totals = self._sum_relation_event_totals(graph)

        classification_distribution: Counter[str] = Counter()
        for _node_id, attrs in graph.nodes(data=True):
            classification_key = attrs.get("classification")
            classification_distribution[
                "null" if classification_key is None else str(classification_key)
            ] += 1

        top_people = []
        for node_id, weighted_degree in sorted(
            weighted_degrees.items(),
            key=lambda item: (-item[1], item[0]),
        )[:20]:
            attrs = graph.nodes[node_id]
            top_people.append(
                {
                    "id": node_id,
                    "name": attrs.get("name"),
                    "classification": attrs.get("classification"),
                    "weighted_degree": weighted_degree,
                    "degree": attrs.get("degree", 0),
                }
            )

        edge_relation_presence = {
            relation_type: sum(
                1
                for _source_id, _target_id, attrs in graph.edges(data=True)
                if attrs.get(f"{relation_type}_count", 0) > 0
            )
            for relation_type in RELATION_DESCRIPTIONS
        }

        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "isolated_nodes": len(isolated_nodes),
            "connected_components": len(components),
            "largest_component_size": max(
                (len(component) for component in components), default=0
            ),
            "relation_event_totals": relation_event_totals,
            "edge_relation_presence": edge_relation_presence,
            "classification_distribution": dict(classification_distribution),
            "top_people_by_weighted_degree": top_people,
        }

    def _sum_relation_event_totals(self, graph: nx.Graph) -> dict[str, int]:
        totals = {relation_type: 0 for relation_type in RELATION_DESCRIPTIONS}
        for _source_id, _target_id, attrs in graph.edges(data=True):
            for relation_type in RELATION_DESCRIPTIONS:
                totals[relation_type] += int(attrs.get(f"{relation_type}_count", 0))
        return totals

    def _increment_edge(
        self, graph: nx.Graph, source_id: int, target_id: int, relation_type: str
    ) -> None:
        if graph.has_edge(source_id, target_id):
            attrs = graph[source_id][target_id]
        else:
            graph.add_edge(
                source_id,
                target_id,
                weight=0,
                initiative_count=0,
                research_group_count=0,
                advisorship_count=0,
            )
            attrs = graph[source_id][target_id]

        attrs["weight"] += 1
        attrs[f"{relation_type}_count"] += 1

    def _ensure_person_node(
        self, graph: nx.Graph, person_id: Optional[int], person_name: Optional[str]
    ) -> None:
        if person_id is None:
            return
        if not graph.has_node(person_id):
            graph.add_node(
                person_id,
                name=person_name,
                classification=None,
                classification_confidence=None,
                was_student=False,
                was_staff=False,
                campus_name=None,
            )
            return

        existing_name = graph.nodes[person_id].get("name")
        if not existing_name and person_name:
            graph.nodes[person_id]["name"] = person_name

    def _unique_people(
        self, people: Iterable[tuple[Any, Any]]
    ) -> dict[int, tuple[int, Optional[str]]]:
        unique_people: dict[int, tuple[int, Optional[str]]] = {}
        for raw_person_id, person_name in people:
            person_id = self._normalize_person_id(raw_person_id)
            if person_id is None:
                continue
            unique_people.setdefault(person_id, (person_id, person_name))
        return unique_people

    @staticmethod
    def _normalize_person_id(person_id: Any) -> Optional[int]:
        if person_id is None:
            return None
        try:
            return int(person_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_campus_name(campus: Any) -> Optional[str]:
        if isinstance(campus, dict):
            return campus.get("name")
        if isinstance(campus, str):
            return campus
        return None
