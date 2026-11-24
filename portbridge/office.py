"""Private coordination plans with explicit review, dependencies and evidence."""

from contextlib import contextmanager
import time
from urllib.parse import urlsplit

from . import PROJECT_LINK
from .discussion import post_notice, require_subscription
from .exchange_fields import Conflict, MAX_SQL_INTEGER, PermissionDenied, REVISION, _integer, _source, _text, _timestamp
from .matching import canonical_url


OFFICE_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    origin_url TEXT NOT NULL,
    comparison_url TEXT NOT NULL,
    basis TEXT NOT NULL,
    created_by INTEGER REFERENCES principals(id),
    created_at INTEGER NOT NULL,
    phase TEXT NOT NULL DEFAULT 'draft',
    priority INTEGER NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 3),
    origin_revision TEXT,
    comparison_revision TEXT,
    source_ready INTEGER NOT NULL DEFAULT 0 CHECK(source_ready IN (0, 1)),
    source_checked_at INTEGER,
    approved_by INTEGER REFERENCES principals(id),
    claimed_by INTEGER REFERENCES principals(id),
    result_id INTEGER REFERENCES results(id),
    decision TEXT,
    decided_by INTEGER REFERENCES principals(id),
    decision_reason TEXT,
    decided_at INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS office_current_pair ON office_plans(problem_id, origin_url, comparison_url)
    WHERE phase IN ('draft', 'active') OR (phase='done' AND decision='adopt');
CREATE INDEX IF NOT EXISTS office_by_topic ON office_plans(problem_id, id);
CREATE TABLE IF NOT EXISTS office_dependencies (
    plan_id INTEGER NOT NULL REFERENCES office_plans(id),
    requires_id INTEGER NOT NULL REFERENCES office_plans(id),
    PRIMARY KEY (plan_id, requires_id), CHECK(plan_id<>requires_id)
);
CREATE INDEX IF NOT EXISTS office_dependents ON office_dependencies(requires_id, plan_id);
"""

PLANS = """
SELECT p.*, a.name AS volunteer, creator.name AS author, approval.name AS reviewer, closer.name AS decided_by_name,
       r.source_url AS report_url, r.revision AS report_revision, r.outcome, r.evidence_kind,
       r.summary AS report_summary, r.platform AS report_platform,
       CASE WHEN r.id IS NULL THEN NULL WHEN w.result_id IS NOT NULL THEN 'withdrawn'
            ELSE coalesce(d.decision, 'pending') END AS report_status,
       (SELECT count(*) FROM office_dependencies od JOIN office_plans next ON next.id=od.plan_id
          WHERE od.requires_id=p.id AND next.phase='active') AS unblocks
FROM office_plans p
LEFT JOIN principals a ON a.id=p.claimed_by
LEFT JOIN principals creator ON creator.id=p.created_by
LEFT JOIN principals approval ON approval.id=p.approved_by
LEFT JOIN principals closer ON closer.id=p.decided_by
LEFT JOIN results r ON r.id=p.result_id
LEFT JOIN decisions d ON d.result_id=r.id
LEFT JOIN withdrawn_results w ON w.result_id=r.id
"""

NEXT_STEPS = {
    "draft": "Проверить цель, согласовать приоритет и зависимости.",
    "waiting_sources": "Подтвердить текущие ревизии обоих источников.",
    "blocked": "Завершить планы, от которых зависит эта проверка.",
    "ready": "Взяться за проверку и сверить условие в своей сборке.",
    "testing": "Воспроизвести проверку и приложить отчёт по зафиксированной версии.",
    "review_report": "Попросить другого участника проверить отчёт.",
    "decision": "Решить, переиспользовать результат, продолжить расследование или отложить.",
}
MAX_DEPENDENCIES = 8
PLAN_LIST_LIMIT = 60


def source_repo(url):
    return "/".join(urlsplit(url).path.split("/")[1:3]).casefold()


def plan_source(value):
    source = canonical_url(_source(value))
    route = urlsplit(source).path.split("/", 3)[3]
    if not route.startswith(("pull/", "commit/")):
        raise ValueError("plan inputs need a public pull request or commit")
    return source


def read_plan(db, ident):
    row = db.execute(PLANS + " WHERE p.id=?", (ident,)).fetchone()
    if row is None:
        raise LookupError("plan not found")
    return row


def dependencies(db, ident):
    return db.execute("""WITH RECURSIVE needs(id) AS (
        SELECT requires_id FROM office_dependencies WHERE plan_id=?
        UNION
        SELECT d.requires_id FROM office_dependencies d JOIN needs ON d.plan_id=needs.id
    )
    SELECT p.id, p.phase, p.decision, p.source_ready,
               (SELECT 1 FROM withdrawn_results WHERE result_id=p.result_id) AS revoked
        FROM needs JOIN office_plans p ON p.id=needs.id ORDER BY p.id""", (ident,)).fetchall()


def dependency_ready(row):
    return row["phase"] == "done" and row["decision"] == "adopt" and row["source_ready"] and not row["revoked"]


def step_for(row, needs):
    phase = row["phase"]
    if phase != "active":
        return phase
    if not row["source_ready"]:
        return "waiting_sources"
    if any(not dependency_ready(dependency) for dependency in needs):
        return "blocked"
    if not row["claimed_by"]:
        return "ready"
    return {"pending": "review_report", "accepted": "decision"}.get(row["report_status"], "testing")


def plan_view(db, row, viewer=None):
    needs = dependencies(db, row["id"])
    state = step_for(row, needs)
    report = None
    if row["report_status"] == "accepted" or (
            row["report_status"] == "pending" and viewer and "review" in viewer["scopes"]):
        report = {"id": row["result_id"], "source_url": row["report_url"], "revision": row["report_revision"],
                  "outcome": row["outcome"], "evidence_kind": row["evidence_kind"],
                  "summary": row["report_summary"], "platform": row["report_platform"]}
    return {key: row[key] for key in ("id", "problem_id", "objective", "origin_url", "comparison_url", "basis",
                                     "priority", "origin_revision", "comparison_revision", "volunteer", "reviewer",
                                     "decision", "decision_reason", "unblocks")} | {
        "author": row["author"] or "PortBridge", "state": state, "next_action": NEXT_STEPS.get(state),
        "sources_available": bool(row["source_ready"]), "source_checked_at": _timestamp(row["source_checked_at"]),
        "requires": [{"id": need["id"], "ready": bool(dependency_ready(need))} for need in needs],
        "report": report, "report_status": row["report_status"], "decided_by": row["decided_by_name"],
        "decided_at": _timestamp(row["decided_at"]),
    }


def outreach(plan):
    """Prepare a pair of public-source-only messages for an approved plan."""
    if not plan["sources_available"] or plan["state"] not in {"ready", "testing", "review_report", "decision"}:
        return []
    origin, comparison = plan["origin_url"], plan["comparison_url"]
    origin_revision, comparison_revision = plan["origin_revision"], plan["comparison_revision"]
    return [{
        "target_url": target,
        "message": (f"{PROJECT_LINK} found a possible cross-project check against {source}. "
                    f"We recorded both revisions: {own_revision} here and {other_revision} there. "
                    "Is there a small public test case and expected result we can compare on both projects?"),
    } for target, source, own_revision, other_revision in (
        (origin, comparison, origin_revision, comparison_revision),
        (comparison, origin, comparison_revision, origin_revision),
    ) if "/pull/" in target]


STAGE_GROUPS = {
    "ready": "available", "draft": "review", "review_report": "review", "decision": "review",
    "testing": "working", "blocked": "waiting", "waiting_sources": "waiting",
}
OVERVIEW_KEYS = ("available", "review", "working", "waiting", "verified", "adopted")


def progress_summary(plans, projects):
    names = {project["repo"].casefold(): project["name"] for project in projects}
    totals, teams = dict.fromkeys(OVERVIEW_KEYS, 0), {}
    needs, milestones = [], []
    for plan in plans:
        labels = []
        stage = STAGE_GROUPS.get(plan["state"])
        if stage:
            labels.append(stage)
            if stage in {"available", "review"}:
                needs.append(plan["id"])
        report = plan["report"] if plan["report_status"] == "accepted" else None
        if (report and plan["sources_available"] and plan["state"] != "superseded"
                and all(dependency["ready"] for dependency in plan["requires"])
                and report["outcome"] == "passed" and report["evidence_kind"] in {"independent", "automated_test"}):
            labels.append("verified")
            milestones.append(plan["id"])
            if plan["decision"] == "adopt":
                labels.append("adopted")
        if not labels:
            continue
        repos = {source_repo(plan[key]) for key in ("origin_url", "comparison_url")}
        for label in labels:
            totals[label] += 1
        for repo in repos:
            counts = teams.setdefault(repo, dict.fromkeys(OVERVIEW_KEYS, 0))
            for label in labels:
                counts[label] += 1
    projects = [{"repo": repo, "name": names.get(repo, repo), **counts} for repo, counts in sorted(teams.items())]
    return {**totals, "by_project": projects, "needs": needs[:8], "milestones": milestones[:8]}


def create_plan(db, problem_id, objective, origin, comparison, basis, actor, now):
    existing = db.execute("""SELECT id FROM office_plans
        WHERE problem_id=? AND origin_url=? AND comparison_url=?
        AND (phase IN ('draft','active') OR (phase='done' AND decision='adopt'))""",
                          (problem_id, origin, comparison)).fetchone()
    if existing:
        return existing["id"], False
    ident = db.execute("""INSERT INTO office_plans
        (problem_id, objective, origin_url, comparison_url, basis, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""", (problem_id, objective, origin, comparison, basis, actor, now)).lastrowid
    post_notice(db, problem_id, f"plan:{ident}:draft",
                f"План №{ident} предложен. Сверьте цель и условия проверки перед началом.",
                now, source_url=comparison)
    return ident, True


def check_sources(db, plan, revisions, now):
    """Pin compared revisions and stop later actions when the inputs move."""
    if plan["phase"] in {"declined", "superseded"}:
        return 0
    current = tuple(revisions.get(plan[key]) for key in ("origin_url", "comparison_url"))
    seen = tuple(value if value and REVISION.fullmatch(value) else None for value in current)
    previous = (plan["origin_revision"], plan["comparison_revision"])
    changed = any(old and new and old != new for old, new in zip(previous, seen))
    if changed or (plan["phase"] == "done" and plan["report_status"] == "withdrawn"):
        db.execute("UPDATE office_plans SET phase='superseded', source_ready=0, source_checked_at=? WHERE id=?",
                   (now, plan["id"]))
        reason = "изменилась ревизия источника" if changed else "исходный отчёт отозван"
        return post_notice(db, plan["problem_id"], f"plan:{plan['id']}:superseded",
                           f"План №{plan['id']} нужно пересмотреть: {reason}. История решения сохранена.", now)
    available = all(seen)
    if available and not all(previous):
        db.execute("""UPDATE office_plans SET origin_revision=?, comparison_revision=?, source_ready=1,
                      source_checked_at=? WHERE id=?""", (*seen, now, plan["id"]))
        comparison = "совпадают" if seen[0] == seen[1] else "различаются"
        return post_notice(db, plan["problem_id"], f"plan:{plan['id']}:sources",
                           f"PortBridge сверил источники плана №{plan['id']}. Ревизии {comparison}. "
                           "В плане сохранены обе версии для отдельной проверки поведения.", now)
    if bool(plan["source_ready"]) != available:
        db.execute("UPDATE office_plans SET source_ready=?, source_checked_at=? WHERE id=?",
                   (available, now, plan["id"]))
    return 0


def reassign_revoked(db, plan, now):
    if (plan["phase"] != "active" or not plan["claimed_by"]
            or plan["report_status"] in {"pending", "accepted"}):
        return 0
    if not db.execute("SELECT 1 FROM revoked_principals WHERE principal_id=?", (plan["claimed_by"],)).fetchone():
        return 0
    db.execute("UPDATE office_plans SET claimed_by=NULL, result_id=NULL WHERE id=?", (plan["id"],))
    return post_notice(db, plan["problem_id"], f"plan:{plan['id']}:reassign:{plan['claimed_by']}",
                       f"План №{plan['id']} снова доступен. У прежнего участника завершился доступ.", now)


def watched_revisions(db, now):
    return dict(db.execute("""SELECT o.url, o.revision FROM office_external_revisions o
        JOIN office_projects p ON p.repo=o.repo
        WHERE p.state='compare' AND o.checked_at>? AND o.revision IS NOT NULL""", (now - 7200,)))


class OfficeStore:
    def __init__(self, exchange):
        self.exchange = exchange

    @contextmanager
    def edit(self, token, scope):
        with self.exchange._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            actor = self.exchange._principal(db, token, scope)
            if "read" not in actor["scopes"]:
                raise PermissionDenied("read access required for office plans")
            yield db, actor, int(time.time())

    def board(self, token, problem_id=None, *, catalog=None):
        with self.exchange._connect() as db:
            db.execute("BEGIN")
            viewer = self.exchange._principal(db, token, "read")
            if problem_id is not None:
                require_subscription(db, viewer, problem_id)
            rows = db.execute(PLANS + """ JOIN topic_subscriptions s ON s.problem_id=p.problem_id
                WHERE s.principal_id=? AND (? IS NULL OR p.problem_id=?)
                ORDER BY p.phase NOT IN ('active', 'draft'), p.priority, unblocks DESC, p.id DESC LIMIT ?""",
                              (viewer["id"], problem_id, problem_id, PLAN_LIST_LIMIT * 3))
            views = [plan_view(db, row, viewer) for row in rows]
            for plan in views:
                plan["outreach_drafts"] = outreach(plan)
            topics = [dict(row) for row in db.execute("""SELECT id, title FROM exchange_topics
                       WHERE decision='accepted' ORDER BY reviewed_at DESC, id LIMIT 60""")]
        if catalog is not None:
            topics = [{"id": card["id"], "title": card["title"]} for card in catalog.problems()] + topics
        order = {"decision": 0, "ready": 1, "review_report": 2, "testing": 3, "draft": 4,
                 "waiting_sources": 5, "blocked": 6}
        views.sort(key=lambda plan: (plan["state"] not in order, plan["priority"], -plan["unblocks"],
                                     order.get(plan["state"], 7), -plan["id"]))
        visible = views[:PLAN_LIST_LIMIT]
        return {"viewer": {"name": viewer["name"], "scopes": viewer["scopes"]},
                "plans": visible, "topics": topics[:PLAN_LIST_LIMIT],
                "progress": progress_summary(visible, catalog.projects() if catalog else ())}

    def propose(self, token, payload, catalog):
        if payload.keys() != {"problem_id", "objective", "origin_url", "comparison_url"}:
            raise ValueError("invalid plan fields")
        origin, comparison = plan_source(payload["origin_url"]), plan_source(payload["comparison_url"])
        if source_repo(origin) == source_repo(comparison):
            raise ValueError("a shared plan needs two repositories")
        objective = _text(payload["objective"], "objective", 240)
        with self.edit(token, "contribute") as (db, actor, now):
            problem = self.exchange._problem(db, payload["problem_id"])
            require_subscription(db, actor, problem)
            ident, created = create_plan(db, problem, objective, origin, comparison, "participant", actor["id"], now)
            row = read_plan(db, ident)
            if not created and row["objective"] != objective:
                raise Conflict("the source pair already has a plan with a different objective")
            revisions = watched_revisions(db, now) | catalog.observed_revisions((origin, comparison))
            check_sources(db, row, revisions, now)
            return plan_view(db, read_plan(db, ident))

    def checked(self, db, actor, ident, catalog, now):
        row = read_plan(db, _integer(ident, "plan_id", 1, MAX_SQL_INTEGER))
        require_subscription(db, actor, row["problem_id"])
        self.exchange._problem(db, row["problem_id"])
        plans = [row, *(read_plan(db, dep["id"]) for dep in dependencies(db, ident))]
        revisions = watched_revisions(db, now) | catalog.observed_revisions(
            plan[key] for plan in plans for key in ("origin_url", "comparison_url"))
        for plan in plans:
            check_sources(db, plan, revisions, now)
        current = read_plan(db, ident)
        reassign_revoked(db, current, now)
        return read_plan(db, ident)

    def review(self, token, ident, decision, priority, requires, catalog):
        if decision not in ("accept", "decline"):
            raise ValueError("invalid plan decision")
        priority = _integer(priority, "priority", 1, 3)
        if not isinstance(requires, list) or len(requires) > MAX_DEPENDENCIES:
            raise ValueError("invalid dependencies")
        required = {_integer(value, "requires", 1, MAX_SQL_INTEGER) for value in requires}
        if decision == "decline" and required:
            raise ValueError("a declined plan has no dependencies")
        with self.edit(token, "review") as (db, actor, now):
            row = self.checked(db, actor, ident, catalog, now)
            if row["phase"] != "draft":
                raise Conflict("only a current draft can be reviewed")
            if row["created_by"] == actor["id"]:
                raise PermissionDenied("another participant must approve the plan")
            for wanted in sorted(required):
                prerequisite = read_plan(db, wanted)
                require_subscription(db, actor, prerequisite["problem_id"])
                if wanted == ident or prerequisite["phase"] not in {"active", "done"}:
                    raise Conflict("choose an already approved prerequisite")
            db.executemany("INSERT INTO office_dependencies VALUES (?, ?)", ((ident, dep) for dep in sorted(required)))
            phase = "active" if decision == "accept" else "declined"
            db.execute("UPDATE office_plans SET phase=?, priority=?, approved_by=? WHERE id=?",
                       (phase, priority, actor["id"], ident))
            message = "согласован" if phase == "active" else "отклонён"
            post_notice(db, row["problem_id"], f"plan:{ident}:{phase}", f"План №{ident} {message}.", now)
            return plan_view(db, read_plan(db, ident))

    def claim(self, token, ident, catalog, *, release=False):
        if type(release) is not bool:
            raise ValueError("release must be a boolean")
        with self.edit(token, "contribute") as (db, actor, now):
            row = self.checked(db, actor, ident, catalog, now)
            state = step_for(row, dependencies(db, ident))
            if (release and row["claimed_by"] == actor["id"] and row["phase"] == "active"
                    and row["report_status"] not in {"pending", "accepted"}):
                db.execute("UPDATE office_plans SET claimed_by=NULL, result_id=NULL WHERE id=?", (ident,))
            elif not release and row["claimed_by"] == actor["id"] and row["phase"] == "active":
                return plan_view(db, row)
            elif not release and state == "ready":
                db.execute("UPDATE office_plans SET claimed_by=? WHERE id=?", (actor["id"], ident))
                post_notice(db, row["problem_id"], f"plan:{ident}:claim:{actor['id']}",
                            f"У плана №{ident} появился участник для проверки. Согласуйте стенд в обсуждении.", now)
            else:
                raise Conflict("plan is not available for this action")
            return plan_view(db, read_plan(db, ident))

    def link_report(self, token, ident, result_id, catalog):
        result_id = _integer(result_id, "result_id", 1, MAX_SQL_INTEGER)
        with self.edit(token, "contribute") as (db, actor, now):
            plan = self.checked(db, actor, ident, catalog, now)
            if plan["claimed_by"] != actor["id"]:
                raise PermissionDenied("only the volunteer can attach a report")
            if result_id == plan["result_id"] and plan["phase"] == "active":
                return plan_view(db, plan)
            if step_for(plan, dependencies(db, ident)) != "testing":
                raise Conflict("plan is not ready for a report")
            report = db.execute("SELECT * FROM results WHERE id=? AND author_id=? AND problem_id=?",
                                (result_id, actor["id"], plan["problem_id"])).fetchone()
            if not report:
                raise LookupError("report not found for that volunteer and topic")
            if report["revision"] != plan["origin_revision"] or source_repo(report["source_url"]) != source_repo(plan["origin_url"]):
                raise Conflict("report is for a different project or revision")
            db.execute("UPDATE office_plans SET result_id=? WHERE id=?", (result_id, ident))
            updated = read_plan(db, ident)
            if updated["report_status"] == "pending":
                post_notice(db, plan["problem_id"], f"plan:{ident}:report:{result_id}",
                            f"План №{ident} ждёт проверяющего. Сверьте версию, условия и результат отчёта.", now)
            return plan_view(db, updated)

    def decide(self, token, ident, decision, reason, catalog):
        if decision not in ("adopt", "investigate", "defer"):
            raise ValueError("invalid adoption decision")
        reason = _text(reason, "reason", 400)
        with self.edit(token, "review") as (db, actor, now):
            row = self.checked(db, actor, ident, catalog, now)
            if row["claimed_by"] == actor["id"]:
                raise PermissionDenied("another participant must decide after the test")
            if step_for(row, dependencies(db, ident)) != "decision":
                raise Conflict("an accepted report for the current plan is required")
            if decision == "adopt" and (row["outcome"] != "passed" or row["evidence_kind"] not in {"independent", "automated_test"}):
                raise Conflict("adoption requires a passing independent or automated test")
            db.execute("""UPDATE office_plans SET phase='done', decision=?, decision_reason=?, decided_by=?,
                          decided_at=? WHERE id=?""", (decision, reason, actor["id"], now, ident))
            post_notice(db, row["problem_id"], f"plan:{ident}:done",
                        f"По плану №{ident} принято решение. Связанные шаги обновлены.", now)
            return plan_view(db, read_plan(db, ident))
