"""Explainable coordination data derived from the reviewed catalog."""

from collections import defaultdict
from hashlib import sha256

from .catalog import source_sync_failed
from .matching import canonical_url


def knowledge_graph(catalog):
    cards = catalog.problems()
    projects = catalog.projects()
    nodes = [{"id": f"project:{p['slug']}", "kind": "project", "label": p["name"], "url": p["url"]} for p in projects]
    nodes.extend({"id": card["id"], "kind": "problem", "label": card["title"], "status": card["status"]}
                 for card in cards)
    edges = []
    for card in cards:
        for ident in card["dependency_ids"]:
            edges.append({"from": card["id"], "to": ident, "kind": "depends_on", "basis": "reviewed_catalog"})
        for solution in card["solutions"]:
            edges.append({"from": f"project:{solution['project']}", "to": card["id"], "kind": "technical_work",
                          "status": solution["status"], "relationship": card.get("relationship", "related_implementation"),
                          "sources": solution["source_refs"]})
    return {"nodes": nodes, "edges": edges}


def recommendations(catalog, *, project="", limit=20):
    cards = {card["id"]: card for card in catalog.problems()}
    dependents = defaultdict(set)
    for card in cards.values():
        if card["status"] != "resolved":
            for requirement in card["dependency_ids"]:
                dependents[requirement].add(card["id"])
    result = []
    for ident, card in cards.items():
        projects = [solution["project"] for solution in card["solutions"]]
        if (project and project not in projects) or card["status"] == "resolved":
            continue
        users = sorted(dependents[ident])
        if users:
            result.append({"id": f"unblock:{ident}", "kind": "unblock_dependency", "problem_id": ident,
                           "projects": projects, "affected_problem_ids": users, "confidence": "reviewed",
                           "reason": "На эту проблему ссылаются открытые карточки как на зависимость.",
                           "next_step": "Подтвердить, какое условие должно выполниться для продолжения зависимых работ.",
                           "decision_by": "maintainers_of_affected_projects"})
        if card.get("relationship") == "shared_symptom":
            result.append({"id": f"compare:{ident}", "kind": "compare_reproduction", "problem_id": ident,
                           "projects": projects, "affected_problem_ids": [], "confidence": "shared_observation",
                           "reason": "Симптом повторился в разных проектах. Причина пока не подтверждена.",
                           "next_step": "Согласовать сравнимый синтетический тест и отметить отличие места остановки.",
                           "decision_by": "maintainers_and_testers"})

    for draft in catalog.outreach():
        pair = [draft["source_project"], draft["target_project"]]
        if project and project not in pair:
            continue
        comparison = draft["mode"] == "comparison"
        comparability = "Сопоставить тест и область проверки в другой архитектуре." if comparison else (
            "Сверить уже принятое изменение с текущей ревизией принимающего проекта.")
        result.append({"id": f"reuse:{draft['id']}", "kind": "reuse_test" if comparison else "review_prior_work",
                       "problem_id": draft["problem_id"], "projects": pair, "affected_problem_ids": [],
                       "confidence": "reviewed_reference", "reason": comparability,
                       "next_step": "Проверить исходный результат и применимость в обсуждении задачи.",
                       "decision_by": draft["target_project"], "source_url": draft["source_url"],
                       "target_url": draft["target_url"], "target_status": draft["target_status"]})

    projects = {row["slug"]: row for row in catalog.projects()}
    open_discussions = {canonical_url(row["url"]) for row in catalog.observations(limit=None)
                        if row["status"] == "open"
                        and not source_sync_failed(projects.get(row["project"], {}), row["url"])}
    for hint in catalog.matches(limit=200):
        if hint.get("basis") != "reference":
            continue
        sources = [hint["left"], hint["right"]]
        pair = [source["project"] for source in sources]
        urls = sorted(canonical_url(source["url"]) for source in sources)
        if (project and project not in pair) or not all(url in open_discussions for url in urls):
            continue
        ident = sha256("\n".join(urls).encode()).hexdigest()[:16]
        result.append({"id": f"overlap:{ident}", "kind": "review_active_overlap", "projects": pair,
                       "affected_problem_ids": [], "confidence": "unreviewed_cross_reference",
                       "reason": "Одно открытое обсуждение ссылается на другое открытое обсуждение.",
                       "next_step": "Сверить границы работы и определить, можно ли переиспользовать проверку.",
                       "decision_by": "participants_of_linked_discussions", "sources": sources})

    seen_failures = set()
    for row in catalog.source_changes():
        url = row["url"]
        if row["kind"] != "test" or url in seen_failures:
            continue
        seen_failures.add(url)
        if (row["previous_status"], row["status"]) != ("success", "failure") or (project and project != row["project"]):
            continue
        result.append({"id": f"ci-change:{row['id']}", "kind": "check_ci_change", "projects": [row["project"]],
                       "affected_problem_ids": [], "confidence": "observed_workflow_status",
                       "reason": "GitHub сначала показывал успех, затем отказ у того же задания или запуска.",
                       "next_step": "Сверить ревизию, номер попытки и причину отказа. Проверить воспроизводимость отдельно.",
                       "decision_by": row["project"], "source_url": url})

    return sorted(result, key=lambda row: (-len(row["affected_problem_ids"]), row["kind"], row["id"]))[:limit]
