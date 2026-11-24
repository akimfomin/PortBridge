"use strict";

const byId = id => document.getElementById(`office-${id}`);
const languageFromURL = () => new URLSearchParams(window.location.search).get("lang") === "ru" ? "ru" : "en";
let language = languageFromURL();
const t = (english, russian) => () => language === "ru" ? russian : english;
const resolveText = value => typeof value === "function" ? value() : value;
const localizedText = new WeakMap();
const languageLinks = document.querySelectorAll("[data-office-language]");
const catalogLinks = document.querySelectorAll("[data-office-catalog]");
const ariaLabels = Array.from(document.querySelectorAll("[data-ru-aria-label]"),
  element => [element, t(element.getAttribute("aria-label"), element.dataset.ruAriaLabel)]);

const states = {
  draft: t("Awaiting approval", "На согласовании"),
  waiting_sources: t("Waiting for sources", "Ждёт источников"),
  blocked: t("Waiting for dependencies", "Ждёт зависимостей"),
  ready: t("Ready to claim", "Можно взять"),
  testing: t("In progress", "В работе"),
  review_report: t("Report under review", "Отчёт на проверке"),
  decision: t("Awaiting a decision", "Нужно решение"),
  done: t("Completed", "Завершён"),
  declined: t("Declined", "Отклонён"),
  superseded: t("Needs reconsideration", "Нужен пересмотр"),
};
const nextSteps = {
  draft: t("Review the objective and agree on priority and dependencies.", "Проверить цель, согласовать приоритет и зависимости."),
  waiting_sources: t("Confirm the current revisions of both sources.", "Подтвердить текущие ревизии обоих источников."),
  blocked: t("Complete the plans this check depends on.", "Завершить планы, от которых зависит эта проверка."),
  ready: t("Claim the check and verify the condition in your build.", "Взяться за проверку и сверить условие в своей сборке."),
  testing: t("Reproduce the check and report the result for the recorded revision.", "Воспроизвести проверку и приложить отчёт по зафиксированной версии."),
  review_report: t("Ask another participant to review the report.", "Попросить другого участника проверить отчёт."),
  decision: t("Decide whether to reuse the result, investigate further, or defer.", "Решить, переиспользовать результат, продолжить расследование или отложить."),
};
const projectStates = {
  mentioned: t("Mentioned in sources", "Найдено в источниках"), found: t("Found on GitHub", "Найдено на GitHub"),
  nominated: t("Nominated", "Предложен"), compare: t("Ready to compare", "К сравнению"), defer: t("Deferred", "Отложен"),
};
const decisions = {
  adopt: t("Reuse", "Переиспользовать"), investigate: t("Investigate further", "Продолжить исследование"), defer: t("Defer", "Отложить"),
};
const outcomes = {
  passed: t("Passed", "Прошла"), failed: t("Failed", "Не прошла"), mixed: t("Mixed", "Смешанный"),
  observed: t("Observation", "Наблюдение"), unknown: t("Unknown", "Неясно"),
};
const evidence = {
  independent: t("Independent check", "Независимая проверка"),
  automated_test: t("Automated test", "Автоматический тест"),
  simulation: t("Simulation", "Учебный сценарий"),
  maintainer_claim: t("Maintainer report", "Заявление сопровождающего"),
  source_observation: t("Source inspection", "Проверка источника"),
};
const errors = {
  400: t("Check the form. Enter GitHub links in their own fields.", "Проверьте поля. Ссылки на GitHub указываются в отдельных полях."),
  401: t("This key was not accepted. Sign in with a valid key.", "Ключ не принят. Войдите с действующим ключом."),
  403: t("This action requires a different role or a topic subscription.", "Для этого действия требуется другая роль или подписка на тему."),
  404: t("Record not found. Check the ID or link.", "Запись не найдена. Проверьте идентификатор или ссылку."),
  409: t("The plan or report changed, or the action no longer applies. Refresh the board.", "План или отчёт изменился, либо действие не подходит к его текущему состоянию. Обновите доску."),
};
const joined = t("You joined the topic.", "Вы присоединились к теме.");
let token = "";
let viewer;
let topic;
let cursor = 0;
let reading;
let titles = new Map();

function setText(element, text) {
  const content = document.createTextNode(resolveText(text) ?? "");
  element.replaceChildren(content);
  if (typeof text === "function") {
    // Keep the surrounding form and its inputs alive when the language changes.
    localizedText.set(element, () => { content.data = text(); });
    element.dataset.officeText = "";
  } else {
    localizedText.delete(element);
    element.removeAttribute("data-office-text");
  }
}

function updateLanguageLinks() {
  for (const link of languageLinks) {
    const url = new URL(window.location.href);
    const choice = link.dataset.officeLanguage;
    if (choice === "ru") url.searchParams.set("lang", "ru");
    else url.searchParams.delete("lang");
    link.href = url.href;
    if (choice === language) link.setAttribute("aria-current", "true");
    else link.removeAttribute("aria-current");
  }
}

function applyLanguage() {
  document.documentElement.lang = language;
  for (const element of document.querySelectorAll("[data-office-text]")) localizedText.get(element)?.();
  for (const [element, label] of ariaLabels) element.setAttribute("aria-label", label());
  for (const link of catalogLinks) link.href = language === "ru" ? "/?lang=ru" : "/";
  updateLanguageLinks();
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) setText(element, text);
  if (className) element.className = className;
  return element;
}

function githubLink(url, label) {
  const link = node("a", label);
  const target = new URL(url);
  if (target.origin === "https://github.com") {
    link.href = target.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  return link;
}

function status(message, error = false) {
  setText(byId("status"), message);
  byId("status").dataset.error = error;
}

async function api(route, body) {
  const key = token;
  const response = await fetch(`/api/v1/exchange/${route}`, {
    method: body ? "POST" : "GET",
    credentials: "omit",
    cache: "no-store",
    headers: {Authorization: `Bearer ${key}`, ...(body && {"Content-Type": "application/json"})},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (key !== token) throw new DOMException("Session ended", "AbortError");
  if (response.ok) return response.json();
  if (response.status === 401 && viewer) leave();
  const message = errors[response.status] || t("The office is temporarily unavailable.", "Штаб временно недоступен.");
  const error = new Error(message());
  error.uiMessage = message;
  throw error;
}

async function perform(control, work, confirmation) {
  control.disabled = true;
  try {
    const message = await work();
    status(confirmation || message || "");
  } catch (error) {
    if (error.name !== "AbortError") {
      status(error.uiMessage || error.message || t("Could not connect to the office.", "Нет соединения со штабом."), true);
    }
  } finally {
    control.disabled = false;
  }
}

function button(label, action, primary = false) {
  const control = node("button", label, primary ? "office-primary" : "");
  control.type = "button";
  control.addEventListener("click", () => perform(control, action));
  return control;
}

function actionForm(title, fields, action) {
  const form = node("form", undefined, "office-form");
  for (const [name, label, options = {}] of fields) {
    const select = options.choices;
    const field = node(select ? "select" : options.multiline ? "textarea" : "input");
    if (select) {
      for (const [value, caption] of Object.entries(select)) {
        const option = node("option", caption);
        option.value = value;
        field.append(option);
      }
    } else if (field.tagName === "INPUT") {
      field.type = options.type || "text";
    }
    field.name = name;
    field.required = !options.optional;
    if (options.max) field.maxLength = options.max;
    if (options.value) field.value = options.value;
    const wrapper = node("label", label);
    wrapper.append(field);
    form.append(wrapper);
  }
  const submit = node("button", title, "office-primary");
  form.append(submit);
  form.addEventListener("submit", event => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    perform(submit, () => action(values), t("Saved.", "Сохранено."));
  });
  return form;
}

function details(title, content) {
  const disclosure = node("details");
  disclosure.append(node("summary", title), content);
  return disclosure;
}

function allowed(scope) {
  return viewer.scopes.includes(scope);
}

async function change(route, body) {
  await api(route, body);
  await refresh();
}

function planActions(plan) {
  const actions = node("div", undefined, "office-actions");
  const act = (label, route, fields) =>
    actions.append(button(label, () => change(route, {plan_id: plan.id, ...fields})));
  const reviewer = allowed("review") && plan.volunteer !== viewer.name;
  if (plan.state === "draft" && reviewer && plan.author !== viewer.name) {
    const selectPriority = {"1": t("1 · High", "1 · Высокий"), "2": t("2 · Normal", "2 · Обычный"), "3": t("3 · Deferred", "3 · Отложенный")};
    actions.append(details(t("Approve plan", "Согласовать план"), actionForm(t("Approve", "Согласовать"), [
      ["priority", t("Priority", "Приоритет"), {choices: selectPriority, value: "2"}],
      ["requires", t("Dependency plan IDs, separated by commas", "Номера зависимостей через запятую"), {optional: true, max: 165}],
    ], fields => change("plan-review", {plan_id: plan.id, decision: "accept", priority: Number(fields.priority),
      requires: fields.requires.trim() ? fields.requires.split(",").map(id => Number(id.trim())) : []}))));
    act(t("Decline plan", "Отклонить план"), "plan-review", {decision: "decline"});
  }
  if (allowed("contribute") && plan.state === "ready") act(t("Claim plan", "Взять в работу"), "plan-claim", {});
  if (allowed("contribute") && plan.volunteer === viewer.name && plan.state === "testing") {
    const report = actionForm(t("Submit for review", "Передать на проверку"), [
      ["source_url", t("Link to the source or test log", "Ссылка на исходную работу или журнал теста"), {type: "url", max: 300, value: plan.origin_url}],
      ["platform", t("Test setup and settings", "Стенд и настройки"), {max: 120}],
      ["evidence_kind", t("Evidence type", "Вид проверки"), {choices: evidence, value: "maintainer_claim"}],
      ["outcome", t("Outcome", "Результат"), {choices: outcomes}],
      ["summary", t("What you tested and what happened", "Что проверили и что получили"), {max: 600, multiline: true}],
    ], async fields => {
      const {result} = await api("submit", {...fields, problem_id: plan.problem_id, revision: plan.origin_revision});
      await change("plan-result", {plan_id: plan.id, result_id: result.id});
    });
    actions.append(details(t("Submit report", "Передать отчёт"), report));
    act(t("Release plan", "Освободить план"), "plan-claim", {release: true});
  }
  if (plan.state === "review_report" && plan.report && reviewer) {
    actions.append(button(t("Accept report", "Принять отчёт"), () => change("review", {result_id: plan.report.id, decision: "accepted"})));
    actions.append(details(t("Return report", "Вернуть отчёт"), actionForm(t("Request changes", "Вернуть на доработку"), [
      ["reason", t("What needs clarification", "Что требуется уточнить"), {max: 400}],
    ], fields => change("review", {result_id: plan.report.id, decision: "rejected", ...fields}))));
  }
  if (plan.state === "decision" && reviewer) {
    const choices = {...decisions};
    if (plan.report.outcome !== "passed" || !["independent", "automated_test"].includes(plan.report.evidence_kind)) delete choices.adopt;
    actions.append(details(t("Make a decision", "Принять решение"), actionForm(t("Save decision", "Сохранить решение"), [
      ["decision", t("Next action", "Дальнейшее действие"), {choices, value: "investigate"}],
      ["reason", t("What the check showed", "Что показала проверка"), {max: 400}],
    ], fields => change("plan-decision", {plan_id: plan.id, ...fields}))));
  }
  return actions;
}

function planCard(plan) {
  const card = node("article", undefined, "office-panel office-card");
  card.id = `office-plan-${plan.id}`;
  const head = node("div", undefined, "office-card-head");
  const label = node("p", t(`Plan #${plan.id} · Priority ${plan.priority}`,
    `План №${plan.id} · Приоритет ${plan.priority}`), "office-meta");
  label.title = plan.problem_id;
  head.append(label, node("span", states[plan.state], "office-state"));
  card.append(head, node("h3", plan.objective));
  if (plan.next_action) card.append(node("p", nextSteps[plan.state] || plan.next_action, "office-next"));
  if (plan.volunteer) card.append(node("p", t(`Volunteer · ${plan.volunteer}`, `Проверяет ${plan.volunteer}`), "office-meta"));
  if (plan.unblocks && plan.state !== "done") {
    card.append(node("p", t(`Accepting the result unblocks ${plan.unblocks} ${plan.unblocks === 1 ? "step" : "steps"}`,
      `После принятия результата разблокируется шагов: ${plan.unblocks}`), "office-meta"));
  }
  const blockers = plan.requires.filter(item => !item.ready).map(item => item.id);
  if (blockers.length) {
    card.append(node("p", t(`Waiting for plans #${blockers.join(", #")}`,
      `Ждёт завершения планов №${blockers.join(", №")}`), "office-meta"));
  }
  const sources = node("div", undefined, "office-actions");
  for (const [url, revision, name] of [
    [plan.origin_url, plan.origin_revision, t("Work under test", "Проверяемая работа")],
    [plan.comparison_url, plan.comparison_revision, t("Related work", "Связанная работа")],
  ]) {
    const link = githubLink(url, revision ? () => `${name()} · ${revision.slice(0, 8)}` : name);
    if (revision) link.title = revision;
    sources.append(link);
  }
  sources.append(button(t("Discussion", "Обсуждение"), () => openThread(plan.problem_id)));
  card.append(sources);
  if (plan.report) {
    const reportLabels = [outcomes[plan.report.outcome], evidence[plan.report.evidence_kind], plan.report.platform];
    card.append(node("p", () => reportLabels.map(resolveText).filter(Boolean).join(" · "), "office-meta"),
      node("p", plan.report.summary), githubLink(plan.report.source_url, t("Report source", "Источник отчёта")));
  }
  if (plan.decision) card.append(node("p", decisions[plan.decision], "office-state"), node("p", plan.decision_reason));
  const actions = planActions(plan);
  if (actions.childElementCount) card.append(actions);
  if (plan.outreach_drafts.length) {
    const drafts = node("div", undefined, "office-list");
    for (const draft of plan.outreach_drafts) {
      const entry = node("div", undefined, "office-entry");
      entry.append(githubLink(draft.target_url, new URL(draft.target_url).pathname.slice(1)),
        node("p", draft.message), button(t("Copy text", "Скопировать текст"), async () => {
          await navigator.clipboard.writeText(draft.message);
          return t("Text copied.", "Текст скопирован.");
        }));
      drafts.append(entry);
    }
    card.append(details(t("GitHub drafts", "Черновики для GitHub"), drafts));
  }
  return card;
}

function nomination(repo = "") {
  return details(t("Suggest a project", "Предложить проект"), actionForm(t("Submit for review", "Добавить к рассмотрению"), [
    ["repo", t("Repository", "Репозиторий"), {max: 140, value: repo}],
    ["evidence_url", t("Link to specific work", "Ссылка на конкретную работу"), {type: "url", max: 300}],
    ["next_step", t("First shared step", "Первый совместный шаг"), {max: 400}],
  ], fields => change("project-nominate", fields)));
}

function projectCard(project) {
  const card = node("article", undefined, "office-entry");
  const heading = node("h3");
  heading.append(githubLink(project.url, project.repo));
  card.append(heading, node("p", projectStates[project.state], "office-meta"));
  if (project.next_step) card.append(node("p", project.next_step), githubLink(project.evidence_url, t("Project work", "Работа проекта")));
  if (project.references) {
    const list = node("ul", undefined, "office-project-refs");
    for (const {url} of project.references) {
      const item = node("li");
      item.append(githubLink(url, new URL(url).pathname.slice(1)));
      list.append(item);
    }
    card.append(list);
  }
  if (project.search_focus) card.append(node("p", project.search_focus.join(" · "), "office-meta"));
  if (["found", "mentioned"].includes(project.state) && allowed("contribute")) card.append(nomination(project.repo));
  if (project.author && allowed("review") && project.author !== viewer.name) {
    const actions = node("div", undefined, "office-actions");
    actions.append(...Object.entries({compare: t("Compare", "Сравнить"), defer: decisions.defer}).filter(([decision]) => decision !== project.state).map(([decision, label]) =>
      button(label, () => change("project-review", {repo: project.repo, decision}))));
    card.append(actions);
  }
  return card;
}

function topicName(id) {
  return titles.get(id) || (id.length > 16 ? `${id.slice(0, 13)}…` : id);
}

async function joinTopic(id) {
  await change("subscribe", {problem_id: id, enabled: true});
  await openThread(id);
  return joined;
}

function topicForms(topics, subscriptions, requests) {
  const container = byId("topic-forms");
  const choices = topics.filter(({id}) => !subscriptions.includes(id));
  const panels = [];
  if (choices.length) {
    const options = Object.fromEntries(choices.map(({id, title}) => [id, title]));
    panels.push(details(t("Find a shared topic", "Найти общую тему"), actionForm(t("Join the selected topic", "Присоединиться к выбранной теме"), [
      ["id", t("Available topics", "Доступные темы"), {choices: options}],
    ], fields => joinTopic(fields.id))));
  }
  if (allowed("contribute")) {
    panels.push(details(t("Suggest a topic", "Предложить тему"), actionForm(t("Submit topic for review", "Передать тему на проверку"), [
      ["source_url", t("First source for this topic", "Первая относящаяся к теме работа"), {type: "url", max: 300}],
      ["title", t("Shared task", "Общая задача"), {max: 160}],
    ], async fields => {
      await api("propose-topic", fields);
      await refresh();
    })));
  }
  if (requests.length) {
    const entries = node("div", undefined, "office-list");
    for (const request of requests) {
      const entry = node("div", undefined, "office-entry");
      const actions = node("div", undefined, "office-actions");
      const review = decision => () => change("review-topic", {source_url: request.source_url, decision});
      actions.append(button(t("Accept topic", "Принять тему"), review("accepted")), button(t("Reject topic", "Отклонить тему"), review("rejected")));
      entry.append(githubLink(request.source_url, request.title), actions);
      entries.append(entry);
    }
    panels.push(details(t("Suggested topics", "Предложенные темы"), entries));
  }
  container.replaceChildren(...panels);
}

const progressLabels = {available: t("ready to claim", "можно взять"), review: t("awaiting review", "ждут решения"), working: t("in progress", "в работе"),
  waiting: t("blocked", "заблокированы"), verified: t("verified", "подтверждены"), adopted: t("ready to use", "к применению")};

function renderProgress(progress, plans) {
  const summary = byId("progress");
  const metrics = node("div", undefined, "office-metrics");
  for (const [key, label] of Object.entries(progressLabels)) {
    metrics.append(node("p", () => `${progress[key]} · ${label()}`, "office-metric"));
  }
  summary.replaceChildren(metrics);
  for (const [title, planIds] of [[t("Where help is needed", "Где нужна помощь"), progress.needs], [t("Verified results", "Подтверждённые результаты"), progress.milestones]]) {
    if (!planIds.length) continue;
    const list = node("ul");
    for (const id of planIds) {
      const plan = plans.find(item => item.id === id);
      const entry = node("li");
      const link = node("a", t(`#${id} · ${plan.objective}`, `№${id} · ${plan.objective}`));
      link.href = `#office-plan-${id}`;
      entry.append(link, node("span", () => ` · ${states[plan.state]()}`, "office-meta"));
      list.append(entry);
    }
    summary.append(node("h3", title), list);
  }
  if (progress.by_project.length) {
    const list = node("ul");
    for (const project of progress.by_project) {
      const item = node("li");
      const counts = Object.entries(progressLabels).filter(([key]) => project[key] > 0);
      item.append(githubLink(`https://github.com/${project.repo}`, project.name),
        node("span", () => ` · ${counts.map(([key, label]) => `${project[key]} ${label()}`).join(" · ")}`, "office-meta"));
      list.append(item);
    }
    const byProject = details(t("By project", "По проектам"), list);
    byProject.open = true;
    summary.append(byProject);
  }
}

async function refresh() {
  const [board, discovery, feeds] = await Promise.all([api("plans"), api("office-projects"), api("subscriptions")]);
  const requests = board.viewer.scopes.includes("review") ? (await api("pending-topics")).topics : [];
  viewer = board.viewer;
  titles = new Map(board.topics.map(({id, title}) => [id, title]));
  byId("viewer").textContent = viewer.name;
  byId("account").hidden = byId("board").hidden = byId("overview").hidden = false;
  byId("login").hidden = true;
  byId("plans").replaceChildren(...(board.plans.length ? board.plans.map(planCard) : [
    node("p", t("No plans yet. Join a topic to see shared work.", "Планов пока нет. Присоединитесь к теме, чтобы увидеть совместную работу."), "office-empty"),
  ]));
  renderProgress(board.progress, board.plans);
  byId("projects").replaceChildren(...(discovery.projects.length ? discovery.projects.map(projectCard) : [
    node("p", t("No suggestions yet.", "Предложений пока нет."), "office-empty"),
  ]));
  byId("subscriptions").replaceChildren(...feeds.subscriptions.map(id => {
    const control = button(topicName(id), () => openThread(id));
    control.title = id;
    return control;
  }));
  topicForms(board.topics, feeds.subscriptions, requests.filter(request => request.author !== viewer.name));
  if (allowed("contribute") && !byId("project-form").childElementCount) byId("project-form").append(nomination());
  if (allowed("contribute") && feeds.subscriptions.length && !byId("plan-form").childElementCount) {
    byId("plan-form").append(details(t("Suggest a plan", "Предложить план"), actionForm(t("Submit for approval", "Передать на согласование"), [
      ["problem_id", t("Topic ID", "ID темы"), {max: 64, value: feeds.subscriptions[0]}],
      ["objective", t("Test objective", "Цель проверки"), {max: 240}],
      ["origin_url", t("Work under test", "Работа, где проверяем"), {type: "url", max: 300}],
      ["comparison_url", t("Related work from another team", "Связанная работа другой команды"), {type: "url", max: 300}],
    ], async fields => {
      await change("plan-propose", fields);
      byId("plan-form").querySelector("details").open = false;
      byId("plan-form").querySelector("form").reset();
    })));
  }
  if (topic && feeds.subscriptions.includes(topic)) await readMessages();
}

async function readMessages() {
  if (!topic || reading === topic) return;
  const current = topic;
  reading = current;
  try {
    const updates = await api(`thread?problem_id=${encodeURIComponent(current)}&after=${cursor}&limit=50`);
    if (topic !== current) return;
    for (const message of updates.messages) {
      const article = node("article", undefined, "office-entry");
      article.append(node("strong", message.author), node("p", message.text, "office-message"));
      if (message.source_url) article.append(githubLink(message.source_url, t("Discussion link", "Ссылка из обсуждения")));
      byId("messages").append(article);
    }
    cursor = updates.next_cursor;
  } finally {
    if (reading === current) reading = undefined;
  }
}

async function openThread(id) {
  topic = id;
  cursor = 0;
  byId("messages").replaceChildren();
  byId("thread").hidden = false;
  byId("thread-title").textContent = topicName(id);
  byId("thread-title").title = id;
  byId("thread-title").focus();
  byId("thread-form").replaceChildren();
  if (allowed("contribute")) {
    const form = actionForm(t("Post to discussion", "Отправить в обсуждение"), [
      ["text", t("Message", "Сообщение"), {max: 1600, multiline: true}],
    ], async fields => {
      await api("message", {...fields, problem_id: id, client_id: crypto.randomUUID()});
      form.reset();
      await readMessages();
    });
    byId("thread-form").append(form);
  }
  await readMessages();
}

function leave() {
  token = "";
  viewer = topic = undefined;
  byId("account").hidden = byId("board").hidden = byId("thread").hidden = true;
  byId("overview").hidden = true;
  titles.clear();
  for (const id of ["plans", "projects", "subscriptions", "messages", "plan-form", "project-form", "thread-form", "topic-forms", "progress"]) {
    byId(id).replaceChildren();
  }
  byId("viewer").textContent = "";
  byId("topic-id").value = "";
  byId("login").hidden = false;
  byId("key").focus();
  status("");
}

for (const element of document.querySelectorAll("[data-ru]")) {
  setText(element, t(element.textContent, element.dataset.ru));
}
for (const link of languageLinks) {
  link.addEventListener("click", event => {
    if (event.defaultPrevented || event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    const choice = link.dataset.officeLanguage;
    if (choice === language) return;
    window.history.pushState(null, "", link.href);
    language = choice;
    applyLanguage();
  });
}
window.addEventListener("popstate", () => {
  const choice = languageFromURL();
  if (choice === language) {
    updateLanguageLinks();
  } else {
    language = choice;
    applyLanguage();
  }
});
window.addEventListener("hashchange", updateLanguageLinks);
applyLanguage();

byId("login").addEventListener("submit", event => {
  event.preventDefault();
  const key = byId("key");
  token = key.value.trim();
  key.value = "";
  perform(event.currentTarget.querySelector("button"), async () => {
    try {
      await refresh();
      byId("plans-title").focus();
    } catch (error) {
      token = "";
      key.focus();
      throw error;
    }
  });
});
byId("subscribe").addEventListener("submit", event => {
  event.preventDefault();
  const input = byId("topic-id");
  const id = input.value.trim().toUpperCase();
  perform(event.currentTarget.querySelector("button"), async () => {
    await joinTopic(id);
    input.value = "";
  }, joined);
});
byId("refresh").addEventListener("click", () => perform(byId("refresh"), refresh, t("Board refreshed.", "Доска обновлена.")));
byId("logout").addEventListener("click", leave);
setInterval(() => {
  if (token && topic && !document.hidden) readMessages().catch(error => {
    if (error.name !== "AbortError") status(error.uiMessage || error.message, true);
  });
}, 5000);
