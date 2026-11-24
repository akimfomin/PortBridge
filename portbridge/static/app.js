'use strict';

const apiRoot = '/api/v1';
const byId = (id) => document.getElementById(id);
const content = byId('content');
const heading = byId('page-title');
const searchField = byId('search');
const projectField = byId('project-filter');
const statusField = byId('status-filter');
const filters = byId('filters');
const viewStatus = byId('view-status');
const summary = byId('summary');
const coordinationSection = byId('coordination');
const projects = new Map();
const snapshots = new Map();
let snapshotSite = null;
let request = null;
let debounce = null;
let summaryData = null;

const problemStates = {
  investigating: 'Исследуется', partial: 'Частично решено', verified: 'Решение проверено', resolved: 'Решено',
};
const solutionStates = {
  reported: 'Сообщено', open: 'Открыто', partial: 'Частичное решение', verified: 'Проверено',
  merged: 'Принято в проект', unknown: 'Статус неизвестен',
};
const evidenceKinds = {
  maintainer_claim: 'Отчёт сопровождающего', automated_test: 'Автоматический тест',
  independent: 'Независимая проверка', source_observation: 'Наблюдение по источнику',
};
const matchStates = {
  suggested: 'Нужна проверка', reviewed_same: 'Связь подтверждена',
  reviewed_symptom: 'Совпадает симптом', reviewed_distinct: 'Разные проблемы',
};
const syncStates = {
  ok: 'Данные обновлены', fresh: 'Данные обновлены', partial: 'Частичное обновление',
  stale: 'Данные из кэша', cached: 'Данные из кэша', error: 'Ошибка обновления',
  'seed-only': 'Исходная подборка', seed: 'Исходная подборка', pending: 'Ожидает обновления',
};
const labels = {
  problems: ['Каталог проблем', 'Исправления и результаты проверок из открытых проектов совместимости Xbox Series с ПК.'],
  partial: ['Где есть задел', 'Проблемы, по которым другая команда проверила решение или продвинулась в его поиске.'],
  matches: ['Схожие проблемы', 'Кандидаты на совпадение. При проверке учитывайте платформу и устройство каждого проекта.'],
  projects: ['Проекты', 'Репозитории, которые отслеживает PortBridge, и свежесть данных GitHub.'],
};
const dateFormat = new Intl.DateTimeFormat('ru-RU', {dateStyle: 'short', timeStyle: 'short'});

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = String(value);
  return node;
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function stamp(value) {
  if (!value) return 'Ещё нет данных';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : dateFormat.format(date);
}

function route() {
  const [path, query] = window.location.hash.replace(/^#\/?/, '').split('?', 2);
  const [view, id] = path.split('/', 2);
  const validView = Object.hasOwn(labels, view) ? view : 'problems';
  return {
    view: validView,
    id: validView === 'problems' && /^[A-Za-z0-9_-]{1,70}$/.test(id || '') ? id : null,
    params: new URLSearchParams(query || ''),
  };
}

function urlFor(id) {
  return `#/problems/${encodeURIComponent(id)}`;
}

function internalLink(title, target, className = '') {
  const anchor = element('a', className, title);
  anchor.href = target;
  return anchor;
}

function githubURL(url) {
  try {
    const target = new URL(url);
    if (target.protocol === 'https:' && target.hostname.toLowerCase() === 'github.com'
        && !target.username && !target.password && !target.port) return target.href;
  } catch {
    // A missing or malformed URL is not a navigation target.
  }
  return null;
}

function githubLink(title, url) {
  const safe = githubURL(url);
  if (!safe) return element('span', '', title);
  const link = internalLink(title, safe);
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}

function repositoryURL(repository) {
  if (!/^[A-Za-z0-9][A-Za-z0-9-]{0,38}\/[A-Za-z0-9_.-]{1,100}$/.test(repository || '')
      || /\/\.{1,2}$/.test(repository)) return null;
  return githubURL(`https://github.com/${repository}`);
}

function badge(state, dictionary) {
  const known = Object.hasOwn(dictionary, state);
  return element('span', known ? `pill pill-${state}` : 'pill', known ? dictionary[state] : 'Статус неизвестен');
}

function projectName(slug) {
  return projects.get(slug)?.name || slug || 'Проект';
}

function projectPill(slug) {
  return element('span', 'project-pill', projectName(slug));
}

function tagRow(values) {
  const row = element('div', 'meta-row');
  list(values).forEach((value) => row.append(element('span', 'tag', value)));
  return row;
}

async function getJSON(url, signal) {
  const response = await fetch(url, {headers: {Accept: 'application/json'}, signal});
  if (!response.ok) {
    const err = new Error('Data request failed');
    err.status = response.status;
    throw err;
  }
  return response.json();
}

function contains(record, query) {
  const haystack = JSON.stringify(record).toLocaleLowerCase();
  const terms = (query || '').toLocaleLowerCase().trim().split(/\s+/);
  return terms.every((term) => {
    if (!/^#[0-9]+$/.test(term)) return haystack.includes(term);
    return new RegExp(`(?:#|/issues/|/pull/)${term.slice(1)}(?![0-9])`).test(haystack);
  });
}

async function readSnapshot(name) {
  if (!snapshots.has(name)) snapshots.set(name, await getJSON(`./data/${name}.json`));
  return snapshots.get(name);
}

async function fetchJSON(path, signal) {
  if (!snapshotSite) return getJSON(`${apiRoot}${path}`, signal);
  const [endpoint, query] = path.split('?', 2);
  const [, name, id] = endpoint.split('/');
  if (!['projects', 'problems', 'matches', 'health', 'coordination', 'outreach'].includes(name)) throw new Error('Unknown snapshot');
  const data = await readSnapshot(name);
  const params = new URLSearchParams(query || '');
  if (name === 'problems') {
    const problems = list(data.problems);
    if (id) {
      const problem = problems.find((entry) => entry.id === decodeURIComponent(id));
      if (problem) return {problem};
      const error = new Error('Unknown problem');
      error.status = 404;
      throw error;
    }
    const project = params.get('project');
    const status = params.get('status');
    return {problems: problems.filter((entry) => contains(entry, params.get('q'))
      && (!project || list(entry.solutions).some((solution) => solution.project === project))
      && (!status || entry.status === status)
      && (params.get('partial') !== '1' || entry.partial_opportunity))};
  }
  if (name === 'matches') return {matches: list(data.matches).filter((entry) => contains(entry, params.get('q')))};
  return data;
}

async function initializeData() {
  const health = await getJSON(`${apiRoot}/health`).catch(() => null);
  if (health) return health;
  const settings = await getJSON('./data/site.json').catch(() => null);
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) return {};
  snapshotSite = settings;
  byId('api-link').href = './api.html';
  const repository = repositoryURL(settings.repository);
  if (repository) {
    const issue = byId('contribute-link');
    const url = new URL(`${repository}/issues/new`);
    if (/^[A-Za-z0-9_-]+\.(yml|yaml|md)$/.test(settings.issue_template || '')) {
      url.searchParams.set('template', settings.issue_template);
    }
    issue.href = url.href;
    issue.hidden = false;
    const guide = byId('contributor-guide');
    guide.href = `${repository}#for-project-contributors`;
    guide.hidden = false;
  }
  return readSnapshot('health').catch(() => ({}));
}

function setHealth(health) {
  const line = byId('sync-status');
  const aged = Date.now() - Date.parse(health.refresh_at) > 2 * 60 * 60 * 1000;
  const variant = health.status === 'ok' && !aged ? 'sync-ok' : (health.status ? 'sync-warning' : '');
  let title = snapshotSite && health.status === 'ok' ? 'Снимок данных GitHub' : syncStates[health.status];
  if (aged) title = 'Данные старше двух часов';
  line.replaceChildren(element('span', `sync-label ${variant}`, title || 'Данные GitHub недоступны'));
  if (health.refresh_at) line.append(element('span', '', stamp(health.refresh_at)));
}

function showSummary(problems) {
  const stats = [
    [projects.size, 'Проекты'],
    [problems.length, 'Проблемы в каталоге'],
    [problems.filter((problem) => problem.partial_opportunity).length, 'Есть задел в других проектах'],
  ];
  summary.replaceChildren(...stats.map(([value, name]) => {
    const block = element('div', 'summary-item');
    block.append(element('span', 'summary-number', value), element('span', 'summary-label', name));
    return block;
  }));
  summary.hidden = false;
}

function showCoordination(data) {
  const reference = data?.coordination?.reference;
  if (!reference?.title) return;
  const headline = element('div', 'card-top');
  headline.append(element('h2', '', 'Общая точка отсчёта'),
    element('span', 'pill', reference.status === 'proposed' ? 'Предложенный ориентир' : 'Ориентир'));
  const source = element('div', 'meta-row');
  source.append(githubLink(reference.title, reference.url));
  if (reference.revision) source.append(element('span', 'identifier', String(reference.revision).slice(0, 12)));
  coordinationSection.append(headline, source);
  for (const detail of [reference.scope, reference.observed]) {
    if (detail) coordinationSection.append(element('p', '', detail));
  }
  const steps = list(data.coordination.steps);
  if (steps.length) {
    const details = element('details');
    const items = element('ol');
    steps.forEach((step) => items.append(element('li', '', step)));
    details.append(element('summary', '', 'Как сравнивать сборки'), items);
    coordinationSection.append(details);
  }
  const current = route();
  coordinationSection.hidden = current.view !== 'problems' || current.id !== null;
}

function stateScreen(title, explanation, retry = false) {
  const section = element('section', retry ? 'empty notice-error' : 'empty');
  section.append(element('h2', '', title), element('p', '', explanation));
  if (retry) {
    const button = element('button', 'retry', 'Повторить');
    button.type = 'button';
    button.addEventListener('click', () => loadView(route()));
    section.append(button);
  }
  content.replaceChildren(section);
}

function problemCard(problem, view) {
  const card = element('article', 'card');
  const top = element('div', 'card-top');
  top.append(element('span', 'identifier', problem.id), badge(problem.status, problemStates));
  const title = element('h2');
  title.append(internalLink(problem.title, urlFor(problem.id)));
  const projectRow = element('div', 'meta-row');
  [...new Set(list(problem.solutions).map((solution) => solution.project))].forEach((slug) => projectRow.append(projectPill(slug)));
  const footer = element('div', 'card-footer');
  const verified = Number(problem.verified_count || 0);
  if (verified > 0) footer.append(element('span', '', `Проектов с проверками: ${verified}`));
  if (view === 'partial' && problem.partial_opportunity) footer.append(badge('partial', {partial: 'Есть задел'}));
  footer.append(internalLink('Сравнить решения →', urlFor(problem.id)));
  card.append(top, title, element('p', '', problem.summary), projectRow);
  if (list(problem.tags).length) card.append(tagRow(problem.tags));
  card.append(footer);
  return card;
}

function drawProblems(problems, view) {
  viewStatus.textContent = `Проблем в списке: ${problems.length}`;
  if (!problems.length) {
    stateScreen('Проблемы не найдены', 'Измените поисковый запрос или сбросьте фильтры.');
    return;
  }
  const wrapper = element('div', 'cards');
  problems.forEach((problem) => wrapper.append(problemCard(problem, view)));
  content.replaceChildren(wrapper);
}

const evidenceOutcomes = {passed: 'Проверка прошла', failed: 'Обнаружен сбой',
  mixed: 'Результаты различаются', observed: 'Наблюдение'};
const githubStates = {open: 'Открыто', closed: 'Закрыто', merged: 'Слито',
  success: 'Проверка прошла', failure: 'Проверка провалилась', cancelled: 'Отменено', in_progress: 'Выполняется'};

function githubStatus(state) {
  if (!state || !githubStates[state.status]) return null;
  return element('span', 'revision', `GitHub: ${githubStates[state.status]} · ${stamp(state.fetched_at)}`);
}

function evidenceItem(evidence) {
  const item = element('li', 'evidence');
  item.append(badge(evidence.kind, evidenceKinds));
  if (evidenceOutcomes[evidence.outcome]) item.append(badge(evidence.outcome, evidenceOutcomes));
  const title = githubLink(evidence.title || 'Первоисточник', evidence.url);
  title.classList.add('evidence-title');
  item.append(title);
  if (evidence.revision) item.append(element('p', 'revision', `Ревизия ${evidence.revision}`));
  if (list(evidence.platforms).length) item.append(tagRow(evidence.platforms));
  if (evidence.observed) {
    const observed = /^\d{4}-\d\d-\d\d[T ]/.test(evidence.observed) ? stamp(evidence.observed) : evidence.observed;
    item.append(element('p', '', observed));
  }
  const state = githubStatus(evidence.github);
  if (state && evidence.kind === 'automated_test') item.append(state);
  return item;
}

function solutionCard(solution) {
  const card = element('article', 'card solution');
  const top = element('div', 'card-top');
  top.append(element('h3', '', projectName(solution.project)), badge(solution.status, solutionStates));
  card.append(top);
  if (solution.summary) card.append(element('p', '', solution.summary));
  if (list(solution.evidence).length) {
    const evidence = element('ul', 'evidence-list');
    solution.evidence.forEach((entry) => evidence.append(evidenceItem(entry)));
    card.append(evidence);
  } else {
    card.append(element('p', '', 'Проверки пока не добавлены.'));
  }
  if (list(solution.source_refs).length) {
    const sources = element('div', 'sources');
    const links = element('ul', 'source-list');
    solution.source_refs.forEach((ref) => {
      const item = element('li');
      item.append(githubLink(ref.title || 'Первоисточник', ref.url));
      const state = githubStatus(ref.github);
      if (state) item.append(document.createTextNode(' · '), state);
      links.append(item);
    });
    sources.append(element('h4', '', 'Первоисточники'), links);
    card.append(sources);
  }
  return card;
}

function draftEditor(message, language) {
  const field = element('textarea');
  field.value = message;
  field.readOnly = true;
  if (language) field.lang = language;
  field.setAttribute('aria-label', 'Текст черновика');
  const status = element('span', 'view-status');
  status.setAttribute('role', 'status');
  const copy = element('button', 'retry', 'Копировать черновик');
  copy.type = 'button';
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(field.value);
      status.textContent = 'Черновик скопирован';
    } catch {
      field.focus();
      field.select();
      status.textContent = 'Текст выделен. Нажмите Ctrl+C, чтобы скопировать его.';
    }
  });
  const actions = element('div', 'draft-actions');
  actions.append(copy, status);
  const fragment = document.createDocumentFragment();
  fragment.append(field, actions);
  return fragment;
}

function answerDraft(problem) {
  const values = [`PortBridge ${problem.id}`, problem.title, '', 'Public references'];
  for (const solution of list(problem.solutions)) {
    const sources = new Set(list(solution.source_refs).map((ref) => githubURL(ref.url)).filter(Boolean));
    for (const source of sources) values.push(`- ${projectName(solution.project)} — ${source}`);
  }
  values.push('', 'Would you confirm which revision and platform this applies to?');
  const details = element('details', 'draft');
  details.append(element('summary', '', 'Черновик для обсуждения'),
    element('p', '', 'Проверьте текст перед отправкой в нужный проект.'), draftEditor(values.join('\n')));
  return details;
}

function outreachCard(draft, problem) {
  const card = element('article', 'card outreach-card');
  const top = element('div', 'card-top');
  const mode = draft.mode === 'reference' ? 'Поделиться результатом' : 'Сопоставить результаты';
  top.append(internalLink(draft.problem_id, urlFor(draft.problem_id), 'identifier'), element('span', 'pill', mode));
  const source = projectName(draft.source_project);
  const target = projectName(draft.target_project);
  card.append(top, element('h3', '', `${source} → ${target}`));
  if (problem) card.append(element('p', '', problem.title));
  const links = element('div', 'meta-row outreach-links');
  links.append(githubLink(`Результат: ${source}`, draft.source_url), githubLink(`Обсуждение: ${target}`, draft.target_url));
  const repository = repositoryURL(snapshotSite?.repository);
  const message = repository && !draft.message.includes(repository)
    ? `${draft.message.trimEnd()}\n\nPortBridge: ${repository}` : draft.message;
  const details = element('details', 'draft');
  details.append(element('summary', '', 'Открыть черновик на английском'), draftEditor(message, 'en'));
  card.append(links);
  if (draft.target_status === 'unobserved') card.append(element('p', '', 'Текущий статус обсуждения не проверен.'));
  card.append(details);
  return card;
}

function showOutreach(data, problems) {
  const known = new Map(problems.map((problem) => [problem.id, problem]));
  const drafts = list(data?.drafts).filter((draft) => known.has(draft?.problem_id) && typeof draft.message === 'string' && draft.message.trim());
  if (data && !drafts.length) return;
  const section = element('section', 'outreach');
  section.append(element('h2', 'section-title', 'Черновики для команд'));
  if (!data) {
    section.append(element('p', 'view-status', 'Не удалось загрузить черновики.'));
  } else {
    section.append(element('p', 'view-status', 'Перед отправкой вручную проверьте источники и статус обсуждения.'));
    const wrapper = element('div', 'cards');
    for (const draft of drafts) wrapper.append(outreachCard(draft, known.get(draft.problem_id)));
    section.append(wrapper);
  }
  content.append(section);
}

function drawProblem(problem) {
  heading.textContent = problem.title;
  byId('page-description').textContent = problem.summary || '';
  viewStatus.textContent = '';
  const detail = element('div', 'detail-top');
  const status = element('div', 'meta-row');
  status.append(element('span', 'identifier', problem.id), badge(problem.status, problemStates));
  detail.append(internalLink('← Каталог проблем', '#/problems', 'detail-back'), status);
  if (snapshotSite && /^PB-[0-9]{4,}$/.test(problem.id)) {
    detail.append(internalLink('Страница для ссылки', `./cases/${problem.id.toLowerCase()}.html`));
  }
  if (list(problem.tags).length || list(problem.platforms).length) {
    detail.append(tagRow([...list(problem.tags), ...list(problem.platforms)]));
  }
  if (list(problem.dependency_ids).length) {
    const dependencies = element('div', 'meta-row');
    dependencies.append(element('span', 'tag', 'Зависимости'));
    problem.dependency_ids.forEach((id) => dependencies.append(internalLink(id, urlFor(id), 'identifier')));
    detail.append(dependencies);
  }
  const comparison = element('div', 'comparison');
  list(problem.solutions).forEach((solution) => comparison.append(solutionCard(solution)));
  const sectionTitle = element('h2', 'section-title', 'Решения и наблюдения по проектам');
  content.replaceChildren(detail, sectionTitle, comparison, answerDraft(problem));
}

function drawMatches(matches) {
  viewStatus.textContent = `Пар в списке: ${matches.length}`;
  if (!matches.length) {
    stateScreen('Схожие проблемы не найдены', 'Попробуйте искать по названию проблемы или проекта.');
    return;
  }
  const wrapper = element('div', 'match-list');
  for (const match of matches) {
    const card = element('article', 'card match-card');
    const top = element('div', 'card-top');
    top.append(badge(match.state, matchStates));
    if (Number.isFinite(match.score)) {
      const percent = Math.round(match.score <= 1 ? match.score * 100 : match.score);
      top.append(element('span', 'score', `Сходство ${percent}%`));
    }
    const pair = element('div', 'match-pair');
    for (const source of [match.left, match.right]) {
      const side = element('div', 'match-side');
      const title = element('h3');
      title.append(githubLink(source.title, source.url));
      side.append(projectPill(source.project), title);
      pair.append(side);
    }
    card.append(top, pair);
    if (match.reason) card.append(element('p', '', match.reason));
    if (match.problem_id) card.append(internalLink(`Карточка ${match.problem_id} →`, urlFor(match.problem_id)));
    wrapper.append(card);
  }
  content.replaceChildren(wrapper);
}

function drawProjects() {
  viewStatus.textContent = `Отслеживается проектов: ${projects.size}`;
  if (!projects.size) {
    stateScreen('Список проектов недоступен', 'Проверьте, запущен ли локальный сервер PortBridge.', true);
    return;
  }
  const wrapper = element('div', 'cards');
  for (const project of projects.values()) {
    const card = element('article', 'card');
    const title = element('h2', '', project.name);
    const stats = element('dl', 'project-status');
    stats.append(element('dt', '', 'Обновление'), element('dd', '', syncStates[project.sync_status] || 'Состояние неизвестно'),
      element('dt', '', 'Последнее успешное получение данных'), element('dd', '', stamp(project.last_success)));
    card.append(title, githubLink(project.repo || 'Репозиторий', project.url));
    if (project.stack) card.append(element('p', '', project.stack));
    if (project.license) card.append(element('p', '', project.license));
    card.append(stats);
    wrapper.append(card);
  }
  content.replaceChildren(wrapper);
}

async function loadView(current, focus = false) {
  request?.abort();
  request = new AbortController();
  const active = request;
  const [title, description] = labels[current.view];
  filters.hidden = current.id !== null || current.view === 'projects';
  filters.classList.toggle('filters-only-search', current.view === 'matches');
  byId('project-group').hidden = current.view === 'matches';
  byId('status-group').hidden = current.view === 'matches';
  summary.hidden = true;
  coordinationSection.hidden = !coordinationSection.hasChildNodes() || current.view !== 'problems' || current.id !== null;
  heading.textContent = current.id ? current.id : title;
  byId('page-description').textContent = current.id ? '' : description;
  document.querySelectorAll('[data-route]').forEach((link) => {
    if (link.dataset.route === current.view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  content.setAttribute('aria-busy', 'true');
  viewStatus.textContent = 'Загрузка…';
  try {
    if (current.view === 'projects') {
      await loadProjects(active.signal);
      if (!active.signal.aborted) drawProjects();
    } else if (current.id) {
      const result = await fetchJSON(`/problems/${encodeURIComponent(current.id)}`, active.signal);
      if (!active.signal.aborted) drawProblem(result.problem);
    } else if (current.view === 'matches') {
      const params = new URLSearchParams({q: current.params.get('q') || ''});
      const result = await fetchJSON(`/matches?${params}`, active.signal);
      if (!active.signal.aborted) drawMatches(list(result.matches));
    } else {
      const params = new URLSearchParams(current.params);
      if (current.view === 'partial') params.set('partial', '1');
      const [result, outreach] = await Promise.all([
        fetchJSON(`/problems?${params}`, active.signal),
        current.view === 'partial' ? fetchJSON('/outreach', active.signal).catch(() => null) : null,
      ]);
      if (active.signal.aborted) return;
      const problems = list(result.problems);
      if (current.view === 'problems' && !current.params.size) summaryData = problems;
      if (current.view === 'problems' && summaryData) showSummary(summaryData);
      drawProblems(problems, current.view);
      if (current.view === 'partial') showOutreach(outreach, problems);
    }
    if (focus && !active.signal.aborted) heading.focus({preventScroll: false});
  } catch (err) {
    if (active.signal.aborted) return;
    viewStatus.textContent = '';
    if (err.status === 404 && current.id) stateScreen('Карточка не найдена', 'Откройте другую проблему из каталога.');
    else stateScreen('Не удалось загрузить данные', 'Проверьте, запущен ли локальный сервер PortBridge.', true);
  } finally {
    if (request === active) content.setAttribute('aria-busy', 'false');
  }
}

async function loadProjects(signal) {
  const result = await fetchJSON('/projects', signal);
  if (signal?.aborted) return;
  projects.clear();
  const options = [new Option('Все проекты', '')];
  list(result.projects).forEach((project) => {
    projects.set(project.slug, project);
    options.push(new Option(project.name, project.slug));
  });
  projectField.replaceChildren(...options);
  projectField.value = route().params.get('project') || '';
}

function restoreFields(current) {
  searchField.value = (current.params.get('q') || '').slice(0, 200);
  projectField.value = current.params.get('project') || '';
  statusField.value = current.params.get('status') || '';
}

function applyFilters() {
  clearTimeout(debounce);
  const current = route();
  const params = new URLSearchParams();
  if (searchField.value.trim()) params.set('q', searchField.value.trim());
  if (current.view !== 'matches') {
    if (projectField.value) params.set('project', projectField.value);
    if (statusField.value) params.set('status', statusField.value);
  }
  const suffix = params.size ? `?${params}` : '';
  history.replaceState(null, '', `#/${current.view}${suffix}`);
  loadView(route());
}

for (const [id, name] of Object.entries(problemStates)) statusField.add(new Option(name, id));
filters.addEventListener('submit', (event) => {
  event.preventDefault();
  applyFilters();
});
searchField.addEventListener('input', () => {
  clearTimeout(debounce);
  debounce = setTimeout(applyFilters, 200);
});
projectField.addEventListener('change', applyFilters);
statusField.addEventListener('change', applyFilters);
byId('reset').addEventListener('click', () => {
  searchField.value = '';
  projectField.value = '';
  statusField.value = '';
  applyFilters();
});
document.querySelector('.skip-link').addEventListener('click', (event) => {
  event.preventDefault();
  heading.focus();
});
window.addEventListener('hashchange', () => {
  clearTimeout(debounce);
  const current = route();
  restoreFields(current);
  loadView(current, true);
});

setHealth({status: 'pending'});
initializeData().then((health) => {
  setHealth(health);
  fetchJSON('/coordination').then(showCoordination).catch(() => {});
  return loadProjects().catch(() => {});
}).then(() => {
  const current = route();
  restoreFields(current);
  loadView(current);
});
