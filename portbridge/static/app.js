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
const sectionFreshness = byId('section-freshness');
const stageField = byId('stage-filter');
const kindField = byId('kind-filter');
const refreshActivity = byId('refresh-activity');
const languageLinks = document.querySelectorAll('[data-language]');
const language = new URLSearchParams(window.location.search).get('lang') === 'ru' ? 'ru' : 'en';
const t = (english, russian) => language === 'ru' ? russian : english;
const projects = new Map();
const snapshots = new Map();
let snapshotSite = null;
let request = null;
let debounce = null;
let summaryData = null;
let activitySignature = '';
let manifestChecked = 0;
const refreshPeriod = 2 * 60 * 1000;

const problemStates = {
  investigating: t('Under investigation', 'Исследуется'), partial: t('Partially resolved', 'Частично решено'),
  verified: t('Fix verified', 'Решение проверено'), resolved: t('Resolved', 'Решено'),
};
const solutionStates = {
  reported: t('Reported', 'Сообщено'), open: t('Open', 'Открыто'), partial: t('Partial fix', 'Частичное решение'),
  verified: t('Verified', 'Проверено'), merged: t('Merged', 'Принято в проект'),
  unknown: t('Unknown status', 'Статус неизвестен'),
};
const evidenceKinds = {
  maintainer_claim: t('Author report', 'Отчёт автора'),
  automated_test: t('Automated test', 'Автоматический тест'),
  independent: t('Independent test', 'Независимая проверка'),
  source_observation: t('Source observation', 'Наблюдение по источнику'),
};
const matchStates = {
  suggested: t('Needs review', 'Нужна проверка'), reviewed_same: t('Confirmed relationship', 'Связь подтверждена'),
  reviewed_symptom: t('Shared symptom', 'Совпадает симптом'), reviewed_distinct: t('Distinct issues', 'Разные проблемы'),
};
const currentData = t('Data is up to date', 'Данные обновлены');
const cachedData = t('Cached data', 'Данные из кэша');
const initialData = t('Initial catalog', 'Исходная подборка');
const syncStates = {
  ok: currentData, fresh: currentData, stale: cachedData, cached: cachedData, seed: initialData, 'seed-only': initialData,
  partial: t('Partially updated', 'Частичное обновление'), error: t('Update failed', 'Ошибка обновления'),
  unavailable: t('GitHub source unavailable', 'Источник GitHub недоступен'),
  pending: t('Waiting for an update', 'Ожидает обновления'),
};
const labels = {
  activity: [t('Project activity', 'Обновления проектов'), t('Recent changes on GitHub, reviewed test results, and work you can help with.',
    'Свежие изменения на GitHub, проверенные результаты и задачи, где можно помочь.')],
  lab: [t('Test Lab', 'Лаборатория тестов'), t('Pick a synthetic check you can run. The instructions and the discussion for sharing results are on GitHub.',
    'Выберите синтетический тест для своего стенда. Инструкция и обсуждение для отчёта находятся на GitHub.')],
  problems: [t('Issue catalog', 'Каталог проблем'), t('Reviewed cases, fixes and test results.',
    'Проверенные карточки, исправления и результаты тестов.')],
  partial: [t('Cross-project leads', 'Где есть задел'), t('Issues where another team has tested a fix or made progress toward one.',
    'Куда применить существующие проверки и какие новые связи стоит рассмотреть.')],
  sources: [t('GitHub sources', 'Источники GitHub'), t('Search the indexed public issues, pull requests and checks.',
    'Поиск по открытым задачам, PR и проверкам из индекса.')],
  matches: [t('Related work', 'Схожие проблемы'), t('Potential matches to review against each project’s platform and architecture.',
    'Кандидаты на совпадение. При проверке учитывайте платформу и устройство каждого проекта.')],
  projects: [t('Projects', 'Проекты'), t('Repositories tracked by PortBridge and the latest data from GitHub.',
    'Репозитории, которые отслеживает PortBridge, и свежесть данных GitHub.')],
};
const dateFormat = new Intl.DateTimeFormat(language, {dateStyle: 'short', timeStyle: 'short'});
const numberFormat = new Intl.NumberFormat(language);
const freshnessLimit = 2 * 60 * 60 * 1000;

function applyPageLanguage() {
  document.documentElement.lang = language;
  if (language === 'en') return;
  byId('api-link').href = '/api/docs';
  byId('feed-link').href = './feed.ru.xml';
  byId('feed-alternate').href = './feed.ru.xml';
  document.querySelectorAll('[data-ru]').forEach((node) => { node.textContent = node.dataset.ru; });
  for (const attribute of ['aria-label', 'placeholder', 'content', 'title']) {
    const localized = `data-ru-${attribute}`;
    document.querySelectorAll(`[${localized}]`).forEach((node) => {
      node.setAttribute(attribute, node.getAttribute(localized));
    });
  }
}

function updateLanguageLinks(hash = window.location.hash) {
  for (const link of languageLinks) {
    const target = new URL(window.location.href);
    const choice = link.dataset.language;
    target.hash = hash;
    if (choice === 'ru') target.searchParams.set('lang', 'ru');
    else target.searchParams.delete('lang');
    link.href = target.href;
    if (choice === language) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
  }
}

function editorial(record, field, locale = language) {
  const original = record[field];
  const translated = record.translations?.[locale]?.[field];
  if (Array.isArray(original)) {
    return Array.isArray(translated) && translated.every((item) => typeof item === 'string') ? translated : original;
  }
  return typeof translated === 'string' && translated.trim() ? translated : original;
}

function hasEnglishCase(problem) {
  const translation = problem.translations?.en;
  return ['title', 'summary'].every((key) => typeof translation?.[key] === 'string' && translation[key].trim());
}

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
  if (!value) return t('No data yet', 'Ещё нет данных');
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? String(value) : dateFormat.format(date);
}

function route() {
  const [path, query] = window.location.hash.replace(/^#\/?/, '').split('?', 2);
  const [view, id] = path.split('/', 2);
  const fallback = path || query ? 'problems' : 'activity';
  const validView = Object.hasOwn(labels, view) ? view : fallback;
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
  return element('span', known ? `pill pill-${state}` : 'pill', known ? dictionary[state] : solutionStates.unknown);
}

function projectName(slug) {
  const project = projects.get(slug);
  return (project && editorial(project, 'name')) || slug || t('Project', 'Проект');
}

function projectPill(slug) {
  return element('span', 'project-pill', projectName(slug));
}

function tagRow(values) {
  const row = element('div', 'meta-row');
  list(values).forEach((value) => row.append(element('span', 'tag', value)));
  return row;
}

async function getJSON(url, signal, cache = 'default') {
  const response = await fetch(url, {headers: {Accept: 'application/json'}, signal, cache});
  if (!response.ok) {
    const err = new Error('Data request failed');
    err.status = response.status;
    throw err;
  }
  return response.json();
}

function searchable(value) {
  return value.toLocaleLowerCase().replace(/https:\/\/github\.com\/xcl-dev\/xcl(?=[/?#"\s]|$)/g,
    'https://github.com/ivall/xcl');
}

function contains(record, query) {
  const haystack = searchable(JSON.stringify(record));
  const terms = searchable(query || '').trim().split(/\s+/);
  return terms.every((term) => {
    if (!/^#[0-9]+$/.test(term)) return haystack.includes(term);
    return new RegExp(`(?:#|/issues/|/pull/)${term.slice(1)}(?![0-9])`).test(haystack);
  });
}

async function readSnapshot(name, signal) {
  const file = snapshotSite?.snapshots?.[name];
  const immutable = typeof file === 'string' && new RegExp(`^${name}-[a-f0-9]{16,64}\\.json$`).test(file);
  if (!immutable) return getJSON(`./data/${name}.json`, signal, 'no-cache');
  if (!snapshots.has(file)) snapshots.set(file, await getJSON(`./data/${file}`, signal));
  return snapshots.get(file);
}

async function checkManifest(signal, force = false) {
  if (!force && Date.now() - manifestChecked < refreshPeriod) return false;
  const settings = await getJSON('./data/site.json', signal, 'no-cache');
  if (!settings || settings.mode !== 'snapshot' || !settings.generated_at) throw new Error('Invalid public snapshot');
  manifestChecked = Date.now();
  const changed = settings.generated_at !== snapshotSite?.generated_at;
  snapshotSite = settings;
  if (changed) summaryData = null;
  byId('sources-link').hidden = !settings.browse_index;
  if (settings.browse_index) {
    byId('search-submit').textContent = t('Search GitHub sources', 'Искать по источникам');
  }
  return changed;
}

async function fetchJSON(path, signal) {
  if (!snapshotSite) return getJSON(`${apiRoot}${path}`, signal, 'no-cache');
  const [endpoint, query] = path.split('?', 2);
  const [, name, id] = endpoint.split('/');
  if (!['projects', 'problems', 'matches', 'health', 'outreach', 'activity', 'ecosystem', 'lab'].includes(name)) {
    throw new Error('Unknown snapshot');
  }
  const data = await readSnapshot(name, signal);
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
  if (!await checkManifest(undefined, true).catch(() => false)) return {};
  const settings = snapshotSite;
  byId('api-link').href = t('./api.html', './api.ru.html');
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
  const aged = Date.now() - Date.parse(health.refresh_at) > freshnessLimit;
  const variant = health.status === 'ok' && !aged ? 'sync-ok' : (health.status ? 'sync-warning' : '');
  let title = snapshotSite && health.status === 'ok' ? t('GitHub data snapshot', 'Снимок данных GitHub') : syncStates[health.status];
  if (aged) title = t('Data is over two hours old', 'Данные старше двух часов');
  line.replaceChildren(element('span', `sync-label ${variant}`, title || t('GitHub data is unavailable', 'Данные GitHub недоступны')));
  if (health.refresh_at) line.append(element('span', '', stamp(health.refresh_at)));
}

function showSummary(problems) {
  const stats = [
    [projects.size, labels.projects[0]],
    [problems.length, t('Catalog entries', 'Проблемы в каталоге')],
    [problems.filter((problem) => problem.partial_opportunity).length, t('Cross-project leads', 'Есть задел в других проектах')],
  ];
  summary.replaceChildren(...stats.map(([value, name]) => {
    const block = element('div', 'summary-item');
    block.append(element('span', 'summary-number', numberFormat.format(value)), element('span', 'summary-label', name));
    return block;
  }));
  summary.hidden = false;
}

function sectionDates(published, checked) {
  sectionFreshness.replaceChildren();
  if (published) {
    sectionFreshness.append(element('span', '', t('Snapshot published', 'Снимок опубликован')), activityTime(published));
  }
  if (checked) {
    sectionFreshness.append(element('span', '', t('Latest successful source check', 'Последняя успешная проверка источника')),
      activityTime(checked));
  }
  sectionFreshness.hidden = !sectionFreshness.childElementCount;
}

function latestChecked(times) {
  return times.filter((value) => typeof value === 'string' && Number.isFinite(Date.parse(value)))
    .sort((first, second) => Date.parse(first) - Date.parse(second)).at(-1);
}

function stateScreen(title, explanation, retry = false) {
  const section = element('section', retry ? 'empty notice-error' : 'empty');
  section.append(element('h2', '', title), element('p', '', explanation));
  if (retry) {
    const button = element('button', 'retry', t('Retry', 'Повторить'));
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
  title.append(internalLink(editorial(problem, 'title'), urlFor(problem.id)));
  const projectRow = element('div', 'meta-row');
  [...new Set(list(problem.solutions).map((solution) => solution.project))].forEach((slug) => projectRow.append(projectPill(slug)));
  const footer = element('div', 'card-footer');
  const verified = Number(problem.verified_count || 0);
  if (verified > 0) {
    const count = numberFormat.format(verified);
    footer.append(element('span', '', t(`Projects with tests: ${count}`, `Проектов с проверками: ${count}`)));
  }
  if (view === 'partial' && problem.partial_opportunity) {
    footer.append(badge('partial', {partial: t('Work to build on', 'Есть задел')}));
  }
  footer.append(internalLink(t('Compare solutions →', 'Сравнить решения →'), urlFor(problem.id)));
  card.append(top, title, element('p', '', editorial(problem, 'summary')), projectRow);
  const tags = list(editorial(problem, 'tags'));
  if (tags.length) card.append(tagRow(tags));
  card.append(footer);
  return card;
}

function drawProblems(problems, view) {
  const count = numberFormat.format(problems.length);
  viewStatus.textContent = t(`Issues: ${count}`, `Проблем в списке: ${count}`);
  if (!problems.length) {
    stateScreen(t('No issues found', 'Проблемы не найдены'),
      t('Try another search or reset the filters.', 'Измените поисковый запрос или сбросьте фильтры.'));
    return;
  }
  const wrapper = element('div', 'cards');
  problems.forEach((problem) => wrapper.append(problemCard(problem, view)));
  content.replaceChildren(wrapper);
}

const evidenceOutcomes = {
  passed: t('Passed', 'Проверка прошла'), failed: t('Failed', 'Обнаружен сбой'),
  mixed: t('Mixed results', 'Результаты различаются'), observed: t('Observation', 'Наблюдение'),
};
const githubStates = {
  open: solutionStates.open, closed: t('Closed', 'Закрыто'), merged: t('Merged', 'Слито'),
  success: evidenceOutcomes.passed, failure: t('Failed', 'Проверка провалилась'),
  cancelled: t('Canceled', 'Отменено'), in_progress: t('In progress', 'Выполняется'),
};

function githubStatus(state) {
  if (!state || !githubStates[state.status]) return null;
  return element('span', 'revision', `GitHub: ${githubStates[state.status]} · ${stamp(state.fetched_at)}`);
}

function evidenceItem(evidence) {
  const item = element('li', 'evidence');
  item.append(badge(evidence.kind, evidenceKinds));
  if (evidenceOutcomes[evidence.outcome]) item.append(badge(evidence.outcome, evidenceOutcomes));
  const title = githubLink(editorial(evidence, 'title') || t('Source', 'Первоисточник'), evidence.url);
  title.classList.add('evidence-title');
  item.append(title);
  if (evidence.revision) item.append(element('p', 'revision', `${t('Revision', 'Ревизия')} ${evidence.revision}`));
  const platforms = list(editorial(evidence, 'platforms'));
  if (platforms.length) item.append(tagRow(platforms));
  const observed = editorial(evidence, 'observed');
  if (observed) {
    item.append(element('p', '', /^\d{4}-\d\d-\d\d[T ]/.test(observed) ? stamp(observed) : observed));
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
  if (projects.get(solution.project)?.sync_status === 'unavailable') {
    card.append(element('p', 'revision', t('GitHub source unavailable. Last recorded evidence is shown.',
      'Источник GitHub недоступен. Показаны ранее сохранённые результаты.')));
  }
  const description = editorial(solution, 'summary');
  if (description) card.append(element('p', '', description));
  if (list(solution.evidence).length) {
    const evidence = element('ul', 'evidence-list');
    solution.evidence.forEach((entry) => evidence.append(evidenceItem(entry)));
    card.append(evidence);
  } else {
    card.append(element('p', '', t('No tests recorded yet.', 'Проверки пока не добавлены.')));
  }
  if (list(solution.source_refs).length) {
    const sources = element('div', 'sources');
    const links = element('ul', 'source-list');
    solution.source_refs.forEach((ref) => {
      const item = element('li');
      item.append(githubLink(editorial(ref, 'title') || t('Source', 'Первоисточник'), ref.url));
      const state = githubStatus(ref.github);
      if (state) item.append(document.createTextNode(' · '), state);
      links.append(item);
    });
    sources.append(element('h4', '', t('Primary sources', 'Первоисточники')), links);
    card.append(sources);
  }
  return card;
}

function bindCopyText(button, field, status, copiedMessage) {
  button.type = 'button';
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(field.value);
      status.textContent = copiedMessage;
    } catch {
      field.hidden = false;
      field.focus();
      field.select();
      status.textContent = t('Text selected. Use your device’s copy command.',
        'Текст выделен. Скопируйте его командой на своём устройстве.');
    }
  });
}

function draftEditor(message, language) {
  const field = element('textarea');
  field.value = message;
  field.readOnly = true;
  if (language) field.lang = language;
  field.setAttribute('aria-label', t('Draft text', 'Текст черновика'));
  const status = element('span', 'view-status');
  status.setAttribute('role', 'status');
  const copy = element('button', 'retry', t('Copy draft', 'Копировать черновик'));
  bindCopyText(copy, field, status, t('Draft copied', 'Черновик скопирован'));
  const actions = element('div', 'draft-actions');
  actions.append(copy, status);
  const fragment = document.createDocumentFragment();
  fragment.append(field, actions);
  return fragment;
}

function answerDraft(problem) {
  const values = [`PortBridge ${problem.id}`, editorial(problem, 'title', 'en'), '', 'Public references'];
  for (const solution of list(problem.solutions)) {
    const sources = new Set(list(solution.source_refs).map((ref) => githubURL(ref.url)).filter(Boolean));
    for (const source of sources) values.push(`- ${projectName(solution.project)} — ${source}`);
  }
  values.push('', 'Would you confirm which revision and platform this applies to?');
  const details = element('details', 'draft');
  details.append(element('summary', '', t('Discussion draft', 'Черновик для обсуждения')),
    element('p', '', t('Review the draft before sharing it with the team.',
      'Проверьте текст перед отправкой в нужный проект.')), draftEditor(values.join('\n'), 'en'));
  return details;
}

function outreachCard(draft, problem) {
  const card = element('article', 'card outreach-card');
  const top = element('div', 'card-top');
  const mode = draft.mode === 'reference' ? t('Share a result', 'Поделиться результатом')
    : t('Compare results', 'Сопоставить результаты');
  top.append(internalLink(draft.problem_id, urlFor(draft.problem_id), 'identifier'), element('span', 'pill', mode));
  const source = projectName(draft.source_project);
  const target = projectName(draft.target_project);
  card.append(top, element('h3', '', `${source} → ${target}`));
  if (problem) card.append(element('p', '', editorial(problem, 'title')));
  const links = element('div', 'meta-row outreach-links');
  links.append(githubLink(`${t('Result', 'Результат')} · ${source}`, draft.source_url),
    githubLink(`${t('Discussion', 'Обсуждение')} · ${target}`, draft.target_url));
  const repository = repositoryURL(snapshotSite?.repository);
  const message = repository && !draft.message.includes(repository)
    ? `${draft.message.trimEnd()}\n\nPortBridge: ${repository}` : draft.message;
  const details = element('details', 'draft');
  details.append(element('summary', '', t('Open draft', 'Открыть черновик на английском')), draftEditor(message, 'en'));
  card.append(links);
  if (draft.target_status === 'unobserved') {
    card.append(element('p', '', t('Check the current discussion status.', 'Текущий статус обсуждения не проверен.')));
  }
  card.append(details);
  return card;
}

function showOutreach(data, problems) {
  const known = new Map(problems.map((problem) => [problem.id, problem]));
  const drafts = list(data?.drafts).filter((draft) => known.has(draft?.problem_id) && typeof draft.message === 'string' && draft.message.trim());
  if (data && !drafts.length) return;
  const section = element('section', 'outreach');
  section.append(element('h2', 'section-title', t('Drafts for teams', 'Черновики для команд')));
  if (!data) {
    section.append(element('p', 'view-status', t('Could not load drafts.', 'Не удалось загрузить черновики.')));
  } else {
    section.append(element('p', 'view-status', t('Check the sources and discussion status before sharing.',
      'Перед отправкой вручную проверьте источники и статус обсуждения.')));
    const wrapper = element('div', 'cards');
    for (const draft of drafts) wrapper.append(outreachCard(draft, known.get(draft.problem_id)));
    section.append(wrapper);
  }
  content.append(section);
}

function drawProblem(problem) {
  heading.textContent = editorial(problem, 'title');
  byId('page-description').textContent = editorial(problem, 'summary') || '';
  viewStatus.textContent = '';
  const detail = element('div', 'detail-top');
  const status = element('div', 'meta-row');
  status.append(element('span', 'identifier', problem.id), badge(problem.status, problemStates));
  detail.append(internalLink(`← ${labels.problems[0]}`, '#/problems', 'detail-back'), status);
  if (/^PB-[0-9]{4,}$/.test(problem.id)) {
    const suffix = language === 'ru' && hasEnglishCase(problem) ? '.ru.html' : '.html';
    detail.append(internalLink(t('Linkable case page', 'Страница для ссылки'), `./cases/${problem.id.toLowerCase()}${suffix}`));
  }
  const tags = [...list(editorial(problem, 'tags')), ...list(editorial(problem, 'platforms'))];
  if (tags.length) detail.append(tagRow(tags));
  if (list(problem.dependency_ids).length) {
    const dependencies = element('div', 'meta-row');
    dependencies.append(element('span', 'tag', t('Dependencies', 'Зависимости')));
    problem.dependency_ids.forEach((id) => dependencies.append(internalLink(id, urlFor(id), 'identifier')));
    detail.append(dependencies);
  }
  const comparison = element('div', 'comparison');
  list(problem.solutions).forEach((solution) => comparison.append(solutionCard(solution)));
  const sectionTitle = element('h2', 'section-title', t('Solutions and observations by project', 'Решения и наблюдения по проектам'));
  content.replaceChildren(detail, sectionTitle, comparison, answerDraft(problem));
}

const browseFile = /^[a-f0-9]{24}$/;

async function browsePosting(generation, kind, roots, key, signal) {
  const encoded = new TextEncoder().encode(key);
  const bytes = await crypto.subtle.digest('SHA-256', encoded);
  const hash = Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, '0')).join('');
  let prefix = hash.slice(0, 2);
  if (!roots.includes(prefix)) return [];
  while (prefix.length <= hash.length) {
    const file = `browse-${generation}-${kind}-terms-${prefix}.json`;
    if (!snapshots.has(file)) snapshots.set(file, await getJSON(`./data/${file}`, signal));
    const shard = snapshots.get(file);
    if (shard.format !== 'PortBridge search shard v1') throw new Error('Invalid public posting');
    if (shard.entries) {
      if (!Object.hasOwn(shard.entries, key)) return [];
      const values = shard.entries[key];
      if (Array.isArray(values)) return values;
      if (!Number.isInteger(values?.parts) || values.parts < 1) throw new Error('Invalid public posting length');
      const items = [];
      for (let start = 0; start < values.parts; start += 4) {
        const files = Array.from({length: Math.min(4, values.parts - start)}, (_, offset) =>
          `browse-${generation}-${kind}-post-${hash}-part-${start + offset}.json`);
        const replies = await Promise.all(files.map((part) => getJSON(`./data/${part}`, signal)));
        for (const reply of replies) {
          if (!Array.isArray(reply.items)) throw new Error('Invalid public posting page');
          items.push(...reply.items);
        }
      }
      return items;
    }
    const digit = hash[prefix.length];
    if (!digit || !list(shard.children).includes(digit)) return [];
    prefix += digit;
  }
  return [];
}

function browseKeys(params, kind) {
  const query = searchable((params.get('q') || '').trim().slice(0, 200));
  const url = githubURL(query);
  const keys = [];
  if (/^[1-9][0-9]*$/.test(query)) keys.push('number:' + query);
  else if (url) {
    const parsed = new URL(url);
    keys.push('url:' + parsed.origin + parsed.pathname.replace(/\/+$/, ''));
  } else {
    for (const token of query.matchAll(/#[0-9]+|[\p{L}\p{N}_]+/gu)) {
      keys.push(token[0].startsWith('#') ? 'number:' + token[0].slice(1) : 'word:' + token[0]);
    }
  }
  const fields = kind === 'matches' ? ['stage', 'project'] : ['project', 'status', 'kind'];
  for (const field of fields) {
    const value = params.get(field);
    if (value && /^[a-z0-9_-]+$/.test(value)) keys.push(`${field}:${value}`);
  }
  return [...new Set(keys)];
}

async function browsePublic(kind, params, signal) {
  const pointer = snapshotSite?.browse_index;
  if (pointer?.version !== 1 || !browseFile.test(pointer.generation)) throw new Error('Unknown browsing index');
  const generation = pointer.generation;
  const manifestKey = `browse-index:${generation}`;
  if (!snapshots.has(manifestKey)) {
    const manifest = await getJSON(`./data/browse-${generation}-index.json`, signal);
    if (manifest.generation !== generation) throw new Error('Public index is updating');
    snapshots.set(manifestKey, manifest);
  }
  const manifest = snapshots.get(manifestKey);
  const dataset = manifest.kinds[kind];
  const size = manifest.page_size;
  if (!dataset || !Number.isInteger(size) || size < 1 || size > 100 || !Number.isInteger(dataset.total)) {
    throw new Error('Invalid browsing dataset');
  }
  const keys = browseKeys(params, kind);
  let ids;
  if (keys.length) {
    // Limit parallel reads. A broad query still uses every selected term.
    const postings = [];
    for (let start = 0; start < keys.length; start += 4) {
      postings.push(...await Promise.all(keys.slice(start, start + 4).map((key) =>
        browsePosting(generation, kind, dataset.roots, key, signal))));
      if (postings.some((posting) => !posting.length)) break;
    }
    postings.sort((a, b) => a.length - b.length);
    const rest = postings.slice(1).map((set) => new Set(set));
    ids = postings[0].filter((id) => Number.isInteger(id) && id >= 0 && id < dataset.total && rest.every((set) => set.has(id)));
  }
  const total = ids?.length ?? dataset.total;
  const pages = Math.max(1, Math.ceil(total / size));
  const page = Math.min(Math.max(1, Number.parseInt(params.get('page'), 10) || 1), pages);
  const offset = (page - 1) * size;
  const selected = ids?.slice(offset, offset + size)
    ?? Array.from({length: Math.min(size, total - offset)}, (_, n) => offset + n);
  const groups = [...new Set(selected.map((id) => Math.floor(id / size)))];
  const rows = new Map();
  for (let start = 0; start < groups.length; start += 4) {
    await Promise.all(groups.slice(start, start + 4).map(async (part) => {
      const file = `browse-${generation}-${kind}-page-${part}.json`;
      if (!snapshots.has(file)) snapshots.set(file, await getJSON(`./data/${file}`, signal));
      rows.set(part, snapshots.get(file).items);
    }));
  }
  return {total, all: dataset.total, page, pages, offset,
    items: selected.map((id) => rows.get(Math.floor(id / size))[id % size])};
}

function drawBrowsePages(result, current) {
  const pagination = element('nav', 'browse-pagination');
  pagination.setAttribute('aria-label', t('Pages of results', 'Страницы результатов'));
  function pageLink(label, page) {
    const params = new URLSearchParams(current.params);
    params.set('page', page);
    return internalLink(label, `#/${current.view}?${params}`, 'retry');
  }
  if (result.page > 1) pagination.append(pageLink(t('Previous', 'Назад'), result.page - 1));
  pagination.append(element('span', '', t(`Page ${result.page} of ${result.pages}`, `Страница ${result.page} из ${result.pages}`)));
  if (result.page < result.pages) pagination.append(pageLink(t('Next', 'Далее'), result.page + 1));
  content.append(pagination);
}

const sourceStates = {
  open: t('Open', 'Открыто'), closed: t('Closed', 'Закрыто'), merged: t('Merged', 'Принято в проект'),
  draft: t('Draft', 'Черновик'), recorded: t('Recorded', 'Записано'), failure: t('Failed', 'Ошибка'),
  success: t('Passed', 'Прошло'), pending: t('Pending', 'Ожидает'), queued: t('Queued', 'В очереди'),
  cancelled: t('Cancelled', 'Отменено'), in_progress: t('In progress', 'В работе'),
  action_required: t('Action required', 'Требует действия'), neutral: t('Neutral', 'Нейтрально'),
  skipped: t('Skipped', 'Пропущено'), timed_out: t('Timed out', 'Истекло время'),
};

const sourceKinds = {pr: 'PR', issue: t('Issue', 'Задача'), commit: t('Commit', 'Коммит'), workflow: t('CI check', 'Проверка CI'),
  test: t('CI check', 'Проверка CI')};

function drawSources(result, current) {
  const total = numberFormat.format(result.total);
  viewStatus.textContent = t(`Sources found: ${total} of ${numberFormat.format(result.all)}`,
    `Найдено источников: ${total} из ${numberFormat.format(result.all)}`);
  if (!result.items.length) {
    stateScreen(t('No GitHub sources found', 'Источники не найдены'), t('Try fewer terms or clear a filter.', 'Сократите запрос или сбросьте фильтр.'));
    return;
  }
  const rows = element('ul', 'source-list');
  for (const source of result.items) {
    const row = element('li', 'card');
    const title = element('h2');
    title.append(githubLink(source.title, source.url));
    const meta = element('div', 'meta-row');
    meta.append(projectPill(source.project), element('span', 'tag', sourceKinds[source.kind] || source.kind),
      badge(source.status, sourceStates));
    if (source.updated_at) meta.append(activityTime(source.updated_at));
    row.append(title, meta, internalLink(t('Find related work', 'Найти связанные работы'),
      `#/matches?${new URLSearchParams({q: source.url})}`));
    rows.append(row);
  }
  content.replaceChildren(rows);
  drawBrowsePages(result, current);
}

const matchReasonText = {
  reference: ['В одном из источников есть прямая ссылка на другой проект.', 'One source links directly to the other project.'],
  shared_revision: ['Совпадает полный идентификатор коммита.', 'The full commit SHA matches.'],
  technical_signal: ['Совпадают технические идентификаторы.', 'Technical identifiers match.'],
  instruction_variants: ['Совпадают семейства инструкций. Сверьте точные варианты и границы теста.',
    'Instruction families match. Check the exact variants and test scope.'],
  technical_terms: ['Совпадают редкие технические термины в описании или заголовке.', 'Distinctive technical terms match in the title or description.'],
  reviewed_same: ['Связь указана в проверенной карточке каталога.', 'A reviewed catalog entry records this relationship.'],
  reviewed_symptom: ['Совпадает симптом. Общая причина не установлена.', 'The sources report a shared symptom. Its cause is still open.'],
};

function matchReason(match) {
  const reason = editorial(match, 'reason');
  const translation = matchReasonText[match.basis] || matchReasonText[match.state];
  if (language === 'ru' || !translation || typeof reason !== 'string' || !reason.startsWith(translation[0])) return reason;
  // The existing snapshot includes matching identifiers as a suffix to the reason.
  const difference = ' Проверьте различия между архитектурами.';
  const details = reason.slice(translation[0].length);
  if (details.endsWith(difference)) {
    return `${translation[1]}${details.slice(0, -difference.length)} Compare the project architectures.`;
  }
  return `${translation[1]}${details}`;
}

function drawMatches(matches, result, current) {
  const count = numberFormat.format(result?.total ?? matches.length);
  viewStatus.textContent = t(`Matching pairs: ${count}`, `Найдено пар: ${count}`);
  if (!matches.length) {
    stateScreen(t('No related work found', 'Схожие проблемы не найдены'),
      t('Try an issue title or project name.', 'Попробуйте искать по названию проблемы или проекта.'));
    return;
  }
  const wrapper = element('div', 'match-list');
  for (const match of matches) {
    const card = element('article', 'card match-card');
    const top = element('div', 'card-top');
    top.append(badge(match.state, matchStates));
    if (match.state === 'suggested') {
      top.append(element('span', 'score', t('Automatic candidate', 'Кандидат по данным индекса')));
    }
    const pair = element('div', 'match-pair');
    for (const source of [match.left, match.right]) {
      const side = element('div', 'match-side');
      const title = element('h3');
      title.append(githubLink(editorial(source, 'title'), source.url));
      side.append(projectPill(source.project), title);
      pair.append(side);
    }
    card.append(top, pair);
    const reason = matchReason(match);
    if (reason) card.append(element('p', '', reason));
    if (match.problem_id) card.append(internalLink(`${t('Issue', 'Карточка')} ${match.problem_id} →`, urlFor(match.problem_id)));
    wrapper.append(card);
  }
  content.replaceChildren(wrapper);
  if (result) drawBrowsePages(result, current);
}

const retryAdvice = t('Try again. For a local installation, check that the PortBridge server is running.',
  'Повторите попытку. Для локальной установки проверьте, запущен ли сервер PortBridge.');

const activityKinds = {
  merged_pr: t('Merged PR', 'PR принят'),
  open_pr: t('Open PR updated', 'Обновлён открытый PR'),
  draft_pr: t('Draft PR updated', 'Обновлён черновик PR'),
  revision_change: t('Revision changed', 'Изменилась ревизия'),
  status_change: t('Status changed', 'Изменился статус'),
  verified_result: t('Reviewed test', 'Проверенный тест'),
};

function activityTime(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return element('span', '', t('No record yet', 'Записей пока нет'));
  const time = element('time', '', stamp(value));
  time.dateTime = value;
  return time;
}

function activityEntry(event) {
  const entry = element('li', 'activity-entry');
  const meta = element('div', 'activity-meta');
  const kind = event.kind === 'open_pr' && event.draft ? 'draft_pr' : event.kind;
  meta.append(badge(kind, activityKinds), element('span', 'activity-project-name', projectName(event.project)), activityTime(event.at));
  entry.append(meta, githubLink(editorial(event, 'title') || t('Source', 'Источник'), event.url));
  const details = element('div', 'activity-meta');
  if (event.kind === 'verified_result') {
    if (event.outcome) details.append(badge(event.outcome, evidenceOutcomes));
    if (event.revision) details.append(element('code', 'identifier', String(event.revision).slice(0, 12)));
    if (list(event.platforms).length) details.append(tagRow(event.platforms));
  }
  if (event.kind === 'revision_change' && event.previous_revision && event.revision) {
    details.append(element('code', 'identifier', `${event.previous_revision.slice(0, 12)} → ${event.revision.slice(0, 12)}`));
  }
  if (event.kind === 'status_change' && githubStates[event.previous_status] && githubStates[event.status]) {
    details.append(element('span', '', `${githubStates[event.previous_status]} → ${githubStates[event.status]}`));
  }
  if (details.childElementCount) entry.append(details);
  const description = editorial(event, 'summary');
  if (description) entry.append(element('p', '', description));
  return entry;
}

function activityProject(project) {
  const card = element('li', 'activity-team');
  const name = element('h3');
  name.append(githubLink(editorial(project, 'name') || project.slug, project.url));
  const counts = project.counts || {};
  const merged = numberFormat.format(counts.merged ?? 0);
  const open = numberFormat.format(counts.open ?? 0);
  const changed = numberFormat.format(counts.changed ?? 0);
  const tested = numberFormat.format(counts.verified ?? 0);
  const totals = element('p', 'activity-team-totals', t(`Merged ${merged} · Open with updates ${open} · Changes ${changed} · Reviewed tests ${tested}`,
    `Принято ${merged} · открытых с обновлениями ${open} · изменений ${changed} · тестов ${tested}`));
  const checks = element('p', 'activity-team-check');
  let status = syncStates[project.status] || t('Update status unavailable', 'Состояние обновления неизвестно');
  if (status === currentData && Date.now() - Date.parse(project.last_success) > freshnessLimit) status = cachedData;
  checks.append(element('span', '', status));
  if (project.last_success) checks.append(element('span', '', t('Last success', 'Последнее обновление')), activityTime(project.last_success));
  card.append(name, totals);
  const latest = project.last_activity;
  if (latest) {
    const source = element('div', 'activity-team-latest');
    const kind = latest.kind === 'open_pr' && latest.draft ? 'draft_pr' : latest.kind;
    const meta = element('div', 'activity-meta');
    meta.append(badge(kind, activityKinds), activityTime(latest.at));
    source.append(meta, githubLink(editorial(latest, 'title') || t('Latest work', 'Последняя работа'), latest.url));
    card.append(source);
  } else {
    card.append(element('p', 'activity-team-empty', t('No recent item in the index.', 'В индексе нет свежих записей.')));
  }
  card.append(checks);
  return card;
}

function activityOpportunity(item) {
  const card = element('article', 'activity-opportunity');
  const title = element('h3');
  const name = editorial(item, 'title') || t('Review the source', 'Сверить источник');
  const detail = editorial(item, 'summary');
  const nextStep = editorial(item, 'next_step');
  title.append(githubLink(name, item.target_url || item.url));
  card.append(title);
  const [sourceProject, targetProject] = list(item.projects);
  if (sourceProject && targetProject) card.append(element('p', 'activity-opportunity-projects', `${projectName(sourceProject)} → ${projectName(targetProject)}`));
  if (detail) card.append(element('p', '', detail));
  if (nextStep) card.append(element('p', 'activity-next-step', nextStep));
  if (item.source_url && item.source_url !== (item.target_url || item.url)) {
    card.append(githubLink(t('Read the evidence', 'Открыть подтверждение'), item.source_url));
  }
  return card;
}

function activityPanel(title, className = '') {
  const panel = element('section', `activity-panel ${className}`.trim());
  panel.append(element('h2', '', title));
  return panel;
}

function activityTimeline(title, events, limit, empty) {
  const panel = activityPanel(title);
  function entries(items) {
    const rows = element('ol', 'activity-timeline');
    rows.append(...items.map(activityEntry));
    return rows;
  }
  panel.append(events.length ? entries(events.slice(0, limit)) : element('p', 'activity-note', empty));
  if (events.length > limit) {
    const more = element('details', 'activity-expand');
    const remaining = numberFormat.format(events.length - limit);
    more.append(element('summary', '', t(`Show ${remaining} more`, `Показать ещё ${remaining}`)), entries(events.slice(limit)));
    panel.append(more);
  }
  return panel;
}

function activityMetrics(counts, labels) {
  const metrics = element('dl', 'activity-metrics');
  for (const [key, label] of labels) {
    const metric = element('div', 'activity-metric');
    metric.append(element('dt', '', label), element('dd', '', numberFormat.format(counts?.[key] ?? 0)));
    metrics.append(metric);
  }
  return metrics;
}

function activityHandoffs(handoffs) {
  const panel = activityPanel(t('PortBridge contributions', 'Вклад PortBridge'));
  const stages = [
    ['delivered', 'delivered_url', t('Submitted', 'Передано в проект')],
    ['independently_reproduced', 'independent_url', t('Independently reproduced', 'Проверено независимо')],
    ['formally_reviewed', 'review_url', t('Reviewed in project', 'Ревью в проекте')],
    ['adopted', 'adopted_url', t('Adopted', 'Внедрено')],
  ];
  panel.append(activityMetrics(handoffs.counts, stages.map(([key, , label]) => [key, label])),
    element('p', 'activity-note', t('Counts cover the contributions below across all dates.',
      'Счётчики учитывают работы из этого списка за всё время.')));
  const items = element('ul', 'activity-timeline');
  for (const handoff of list(handoffs.items)) {
    const row = element('li', 'activity-entry');
    const links = element('div', 'activity-handoff-proof');
    for (const [, field, label] of stages) {
      if (handoff[field]) links.append(githubLink(label, handoff[field]));
    }
    row.append(element('span', 'activity-meta activity-project-name', projectName(handoff.project)),
      element('h3', '', editorial(handoff, 'title') || handoff.problem_id), links);
    items.append(row);
  }
  panel.append(items);
  return panel;
}

const radarKinds = {
  recheck_revision: t('New revision', 'Новая ревизия'),
  review_report: t('Review a report', 'Сверить отчёт'),
  cover_hardware: t('Hardware check', 'Проверка на оборудовании'),
  compare_sources: t('Compare sources', 'Сопоставить источники'),
};
const radarProofs = {
  target: t('Open discussion', 'Открыть обсуждение'),
  report: t('Open report', 'Открыть отчёт'),
  procedure: t('Test procedure', 'Порядок проверки'),
  tested_revision: t('Tested revision', 'Проверенная версия'),
  pinned_revision: t('Pinned revision', 'Закреплённая версия'),
  comparison: t('Comparison source', 'Источник для сравнения'),
};
const radarPriority = {
  high: t('High priority', 'Высокий приоритет'),
  normal: t('Test queue', 'Очередь проверок'),
  exploratory: t('Research lead', 'Кандидат для исследования'),
};
const radarSelection = {kind: '', equipment: ''};

function radarAction(action) {
  const card = element('li', 'activity-opportunity');
  const check = action.freshness || {};
  const verify = action.state === 'verify_sources' || check.state !== 'fresh'
    || Date.now() - Date.parse(check.checked_at) > freshnessLimit;
  const meta = element('div', 'activity-meta');
  meta.append(badge(action.kind, radarKinds), element('span', '', radarPriority[action.priority]));
  if (verify) meta.append(element('strong', '', t('Check the source first', 'Сначала сверьте источник')));
  if (check.checked_at) meta.append(activityTime(check.checked_at));
  const title = element('h3');
  const name = editorial(action, 'title');
  title.append(labTaskID.test(action.task_id || '') ? internalLink(name, labTaskPath(action.task_id))
    : githubLink(name, action.target_url));
  card.append(meta, title);
  const hardware = list(action.equipment).map((kind) => labEquipment[kind] || kind);
  if (hardware.length) card.append(element('p', 'activity-opportunity-projects', hardware.join(' · ')));
  const summary = editorial(action, 'summary');
  if (summary) card.append(element('p', '', summary));
  if (!verify) card.append(element('p', 'activity-next-step', editorial(action, 'next_step')));
  const criterion = editorial(action, 'criterion');
  if (criterion) card.append(element('p', '', criterion));
  const links = element('div', 'activity-handoff-proof');
  for (const item of list(action.sources)) {
    if (Object.hasOwn(radarProofs, item.role)) {
      const label = item.role === 'comparison' && item.status === 'closed'
        ? t('Comparison source (closed)', 'Источник для сравнения (закрыт)') : radarProofs[item.role];
      links.append(githubLink(label, item.url));
    }
  }
  card.append(links);
  return card;
}

function activityRadar(radar) {
  const panel = activityPanel(t('Research radar', 'Радар исследований'));
  const actions = list(radar.actions);
  const bar = element('div', 'lab-bar');
  const rows = element('ul', 'activity-timeline');
  const count = element('p', 'lab-count');
  count.setAttribute('role', 'status');

  function render() {
    const visible = actions.filter((action) => (!radarSelection.kind || action.kind === radarSelection.kind)
      && (!radarSelection.equipment || list(action.equipment).includes(radarSelection.equipment)));
    const amount = numberFormat.format(visible.length);
    count.textContent = visible.length
      ? t('Actions shown ' + amount, 'Задач показано ' + amount)
      : t('No actions match these filters.', 'По этим фильтрам задач нет.');
    rows.replaceChildren(...visible.map(radarAction));
  }

  function filter(name, labelText, choices) {
    const group = element('div', 'filter-group');
    const input = element('select');
    input.id = 'radar-' + name;
    const label = element('label', '', labelText);
    label.htmlFor = input.id;
    input.append(new Option(t('All', 'Все'), ''));
    for (const [value, option] of choices) input.append(new Option(option, value));
    input.value = radarSelection[name];
    input.addEventListener('change', () => {
      radarSelection[name] = input.value;
      render();
    });
    group.append(label, input);
    return group;
  }

  bar.append(filter('kind', t('Action', 'Действие'), Object.entries(radarKinds)),
    filter('equipment', t('Equipment', 'Оборудование'), Object.entries(labEquipment)));
  panel.append(bar, count, rows);
  render();
  return panel;
}

function showCurrentLeads(data, params) {
  if (!data) return;
  const panel = activityPanel(t('Where work can advance now', 'Где можно продвинуть работу'));
  const items = element('ul', 'activity-opportunity-list');
  const project = params.get('project');
  const relevant = (row) => contains(row, params.get('q')) && (!project || list(row.projects).includes(project));
  const opportunities = list(data.opportunities).filter(relevant);
  for (const item of opportunities) items.append(activityOpportunity(item));
  const actions = list(data.radar?.actions).filter(relevant);
  for (const action of actions) items.append(radarAction(action));
  if (!actions.length && !opportunities.length) {
    panel.append(element('p', 'activity-note', t('No current opportunity matches these filters.', 'По этим фильтрам сейчас нет активных возможностей.')));
  }
  panel.append(items);
  const history = element('h2', 'section-title', t('Reviewed cases to build on', 'Проверенные карточки и история'));
  content.prepend(panel, history);
}

function researchHighlights(items) {
  const panel = activityPanel(t('Engineering results', 'Инженерные результаты'));
  const results = element('ul', 'activity-timeline');
  for (const item of items) {
    const row = element('li', 'activity-entry');
    const h = element('h3');
    h.append(internalLink(editorial(item, 'title'), urlFor(item.problem_id)));
    const links = element('div', 'activity-handoff-proof');
    for (const [key, label] of [
      ['delivered_url', t('Upstream discussion', 'Обсуждение команды')],
      ['independent_url', t('Independent check', 'Независимая проверка')],
      ['adopted_url', t('Adoption evidence', 'Подтверждение внедрения')],
    ]) {
      if (item[key]) links.append(githubLink(label, item[key]));
    }
    const stage = element('div', 'activity-meta');
    stage.append(element('span', 'tag', t('Shared with the project', 'Передано команде')));
    if (item.checked_at && sourceStates[item.source_state]) {
      stage.append(element('span', '', sourceStates[item.source_state]), activityTime(item.checked_at));
    }
    row.append(h, stage, element('p', '', editorial(item, 'summary')), links);
    results.append(row);
  }
  panel.append(results);
  return panel;
}

function showActivity(data, quiet = false) {
  const {as_of, window_start, ...observed} = data;
  const signature = JSON.stringify(observed);
  setHealth({status: data.health, refresh_at: data.refreshed_at});
  if (quiet && signature === activitySignature) return false;
  activitySignature = signature;
  const board = element('div', 'activity-board');
  const windowDays = numberFormat.format(data.window_days);
  const stats = element('section', 'activity-overview');
  const overviewHeading = element('div', 'activity-overview-head');
  const freshness = element('p', 'activity-freshness');
  freshness.append(element('span', '', t('Last sync attempt', 'Последняя попытка обновления')), activityTime(data.refreshed_at));
  overviewHeading.append(element('h2', '', t(`Last ${windowDays} days`, `Последние ${windowDays} дней`)), freshness);
  stats.append(overviewHeading);
  const metrics = activityMetrics(data.counts, [
    ['merged', t('Merged PRs', 'Принятые PR')],
    ['open', t('Open PRs with updates', 'Открытые PR с обновлениями')],
    ['changed', t('Revision or status changes', 'Смены ревизий или статусов')],
    ['verified', t('Reviewed test results', 'Проверенные результаты')],
  ]);
  stats.append(metrics, element('p', 'activity-note', t('Counts cover indexed public sources. Reviewed results include failed tests.',
    'Подсчёт по открытым источникам в индексе. Проверенные результаты включают неудачные прогоны.')));
  const columns = element('div', 'activity-columns');
  const events = list(data.events);
  const results = activityTimeline(t('Reviewed results', 'Проверенные результаты'),
    events.filter((event) => event.kind === 'verified_result'), 3,
    t('No recent reviewed tests in the catalog.', 'За этот период в каталоге нет проверенных тестов.'));
  const feed = activityTimeline(t('Recent changes', 'Свежие изменения'),
    events.filter((event) => event.kind !== 'verified_result'), 8,
    t('No recent changes in the index.', 'В индексе нет свежих изменений.'));
  const opportunities = activityPanel(t('Where you can help', 'Где можно помочь'), 'activity-actions');
  const suggestions = list(data.opportunities).slice(0, 3);
  if (suggestions.length) opportunities.append(...suggestions.map(activityOpportunity));
  else opportunities.append(element('p', 'activity-note', t('No open work linked to a reviewed test in this snapshot.', 'В этом снимке нет открытых задач, связанных с проверенным тестом.')));
  opportunities.append(internalLink(t('Find a test for your setup', 'Подобрать тест для своего стенда'), '#/lab', 'activity-more'));
  const repository = repositoryURL(snapshotSite?.repository);
  if (repository) {
    const queue = new URL(`${repository}/issues`);
    queue.searchParams.set('q', 'is:issue is:open label:"help wanted"');
    const help = githubLink(t('Open tasks for volunteers', 'Открытые задачи для участников'), queue.href);
    help.classList.add('activity-more');
    opportunities.append(help);
  }
  opportunities.append(internalLink(t('Browse cross-project leads', 'Смотреть задачи между командами'), '#/partial', 'activity-more'));
  columns.append(results, opportunities);
  const teams = activityPanel(t('Across the projects', 'По проектам'), 'activity-projects');
  const teamList = element('ul', 'activity-team-list');
  teamList.append(...list(data.projects).map(activityProject));
  if (teamList.childElementCount) teams.append(teamList);
  else teams.append(element('p', 'activity-note', t('Project data is unavailable.', 'Данные о проектах недоступны.')));
  const start = element('div', 'activity-start');
  start.append(internalLink(t('Choose a test to run', 'Выбрать тест для своего стенда'), '#/lab', 'lab-primary'),
    internalLink(t('Browse reviewed cases', 'Посмотреть проверенные карточки'), '#/problems', 'retry'));
  if (snapshotSite?.browse_index) start.append(internalLink(t('Browse public GitHub sources', 'Открыть индекс GitHub'), '#/sources', 'retry'));
  board.append(start, stats);
  if (list(data.research).length) board.append(researchHighlights(data.research));
  board.append(columns);
  if (data.radar) board.append(activityRadar(data.radar));
  board.append(feed, teams);
  if (list(data.handoffs?.items).length) board.append(activityHandoffs(data.handoffs));
  viewStatus.textContent = '';
  content.replaceChildren(board);
  return true;
}

const capabilityKinds = {
  source: t('Source inspected', 'Исходник сверён'),
  reported: t('Author report', 'Отчёт автора'),
  tested: t('Test result', 'Результат теста'),
  merged: t('Merged change', 'Принято в проект'),
};

function drawEcosystem(data) {
  const section = element('section', 'ecosystem-panel');
  const capabilities = element('details', 'activity-panel');
  const leads = element('details', 'activity-panel');
  capabilities.append(element('summary', '', t('Technical capability map', 'Карта технических возможностей')),
    element('p', 'activity-note', t('Each entry covers the linked test or code. Areas with no entry remain unverified here.',
      'Каждая запись относится к конкретному тесту или коду. Пустые направления ещё не сверены.')));
  for (const area of list(data.areas)) {
    if (!area?.name?.[language]) continue;
    const records = list(data.capabilities).filter((entry) => entry.area === area.id);
    const entries = element('ul', 'ecosystem-list');
    for (const entry of records) {
      const row = element('li');
      row.append(githubLink(projectName(entry.project), entry.evidence),
        element('span', '', editorial(entry, 'scope')),
        element('small', '', capabilityKinds[entry.kind] || t('Evidence', 'Источник')));
      entries.append(row);
    }
    capabilities.append(element('h3', '', area.name[language]));
    capabilities.append(records.length ? entries : element('p', 'activity-note', t('No evidence yet.', 'Данных пока нет.')));
  }
  const count = numberFormat.format(data.counts.lead_repositories);
  leads.append(element('summary', '', t(`Repository leads (${count})`, `Репозитории на проверку (${count})`)),
    element('p', 'activity-note', t('Review repository scope, license and sources before tracking a lead.',
      'Перед подключением проверьте назначение, лицензию и источники проекта.')));
  const names = new Map(list(data.sources).map((source) => [source.id, source.name]));
  const statuses = {ok: t('Last check succeeded', 'Источник ответил'), cached: cachedData,
    failed: t('Unavailable', 'Недоступно'), pending: syncStates.pending};
  const sourceStatus = element('ul', 'ecosystem-list ecosystem-sources');
  for (const source of list(data.sources)) {
    const state = [statuses[source.state] || statuses.pending, source.last_success && stamp(source.last_success)].filter(Boolean);
    sourceStatus.append(element('li', '', `${source.name} · ${state.join(' · ')}`));
  }
  leads.append(sourceStatus);
  const entries = element('ul', 'ecosystem-list');
  const rows = list(data.leads);
  for (const lead of rows) {
    const row = element('li');
    const sources = list(lead.sources).map((id) => names.get(id)).filter(Boolean);
    if (list(lead.references).length) sources.push(t('Linked by a tracked project', 'Есть ссылка из отслеживаемого проекта'));
    row.append(githubLink(lead.repo, lead.url), element('span', '', sources.join(' · ')));
    entries.append(row);
  }
  leads.append(entries);
  if (rows.length < data.counts.lead_repositories) {
    const shown = numberFormat.format(rows.length);
    leads.append(element('p', 'activity-note', t(`Showing ${shown} of ${count} leads.`, `Показано ${shown} из ${count} кандидатов.`)));
  }
  section.append(capabilities, leads);
  return section;
}

function drawProjects(ecosystem) {
  const count = numberFormat.format(projects.size);
  viewStatus.textContent = t(`Tracked projects: ${count}`, `Отслеживается проектов: ${count}`);
  if (!projects.size) {
    stateScreen(t('Project list is unavailable', 'Список проектов недоступен'), retryAdvice, true);
    return;
  }
  const wrapper = element('div', 'cards');
  for (const project of projects.values()) {
    const card = element('article', 'card');
    const title = element('h2', '', projectName(project.slug));
    const stats = element('dl', 'project-status');
    stats.append(element('dt', '', t('Update status', 'Обновление')),
      element('dd', '', syncStates[project.sync_status] || t('Unknown status', 'Состояние неизвестно')),
      element('dt', '', t('Last successful update', 'Последнее успешное получение данных')),
      element('dd', '', stamp(project.last_success)));
    card.append(title, githubLink(project.repo || t('Repository', 'Репозиторий'), project.url));
    const stack = editorial(project, 'stack');
    if (stack) card.append(element('p', '', stack));
    if (project.license) card.append(element('p', '', project.license));
    card.append(stats);
    wrapper.append(card);
  }
  const showMap = Number.isInteger(ecosystem?.counts?.lead_repositories)
    && ['areas', 'capabilities', 'leads', 'sources'].every((key) => Array.isArray(ecosystem[key]));
  content.replaceChildren(...(showMap ? [drawEcosystem(ecosystem), wrapper] : [wrapper]));
}

const labEquipment = {
  amd: t('AMD graphics', 'Видеокарта AMD'), cpu: t('CPU only', 'Только процессор'),
  intel: t('Intel graphics', 'Видеокарта Intel'), nvidia: t('NVIDIA graphics', 'Видеокарта NVIDIA'),
};
const portbridgeRepository = 'https://github.com/akimfomin/PortBridge';
const portbridgePublicSite = 'https://akimfomin.github.io/PortBridge/';
const labTaskID = /^[a-z0-9-]{1,80}$/;
function labTaskPath(id, equipment = '', showAll = false) {
  const params = new URLSearchParams({task: id});
  if (equipment) params.set('equipment', equipment);
  if (showAll) params.set('status', 'all');
  return `#/lab?${params}`;
}
const labStatus = {
  needs_run: t('A test run is needed', 'Нужен прогон'),
  needs_revision: t('Awaiting combined revision', 'Ждём объединённую версию'),
  awaiting_review: t('Awaiting team review', 'Ждём ответа команды'),
  blocked: t('Source unavailable', 'Источник недоступен'),
};
const labEvidence = {
  assembled_offline: t('Assembled offline', 'Собрано без запуска'),
  author_cpu: t('CPU run by the author', 'Тест автора на процессоре'),
  author_gpu: t('GPU run by the author', 'Тест автора на видеокарте'),
  reviewed_gpu: t('Independent GPU result', 'Независимый тест на видеокарте'),
  reviewed_cpu: t('Independent CPU result', 'Независимый тест на процессоре'),
};
const labAdoption = {
  pending: t('Adoption pending', 'Решение о переносе ожидается'),
  adopted: t('Adopted by the team', 'Принято командой'),
  declined: t('Declined by the team', 'Отклонено командой'),
};
const labReportStates = {
  fresh: t('Discussion checked', 'Обсуждение проверено'),
  stale: t('Latest check failed. Showing the last successful check.', 'Последняя проверка не удалась. Показаны данные предыдущей успешной проверки.'),
  unavailable: t('Could not check the reporting discussion.', 'Не удалось проверить обсуждение с отчётами.'),
  unchecked: t('The reporting discussion has yet to be checked automatically.', 'Автоматическая проверка обсуждения ещё не проводилась.'),
};
const labCoverageStates = {
  covered: t('Covered', 'Покрыто'), reported: t('Report needs review', 'Отчёт ждёт проверки'),
  partial: t('Some tests remain', 'Часть тестов ещё нужна'),
  missing: t('Run needed', 'Нужен прогон'), contradicted: t('Failure needs review', 'Нужен разбор сбоя'),
};
const labReportAuthority = {
  approved: t('Approved reporter', 'Согласованный автор отчёта'),
  community: t('Community report', 'Отчёт сообщества'),
};
const labReportOutcomes = {
  pass: evidenceOutcomes.passed,
  fail: evidenceOutcomes.failed,
  partial: t('Partial coverage', 'Частичная проверка'),
};

const labAgentPrompt = t(
  `Open ${portbridgeRepository} and read AGENTS.md. Choose one open Test Lab check that fits my equipment. `
  + 'Check the original discussion, the exact revision and whether anyone is already running it. '
  + 'Use synthetic inputs in a separate checkout. Record the expected and observed result, the hardware and the revision. '
  + 'Prepare a short handoff that says how PortBridge helped and links to it. Ask before posting it.',
  `Открой ${portbridgeRepository} и прочитай AGENTS.md. Подбери одну открытую проверку из лаборатории под мой компьютер. `
  + 'Сверь исходное обсуждение, точную версию и не взялся ли кто-то за эту проверку. '
  + 'Используй синтетические данные и отдельную копию проекта. Запиши ожидаемый и фактический результат, стенд и версию. '
  + 'Подготовь короткое сообщение о том, чем помог PortBridge, со ссылкой на него. Спроси перед публикацией.',
);

function labAgentEntry(task) {
  const section = element('section', 'lab-agent');
  const actions = element('div', 'lab-agent-actions');
  const copy = element('button', 'lab-primary', task
    ? t('Copy this task for an agent', 'Копировать эту проверку для агента')
    : t('Copy instructions for finding a test', 'Копировать инструкцию по выбору проверки'));
  const prompt = element('textarea');
  prompt.value = labAgentPrompt;
  if (task) {
    const page = portbridgePublicSite + labTaskPath(task.id);
    const intro = t(
      `Open ${page}. In MCP use portbridge_lab with task "${task.id}", or find the same ID in https://akimfomin.github.io/PortBridge/data/lab.json. `
      + 'Check whether the linked discussion still needs this run and confirm the exact revision. '
      + 'Use only synthetic inputs in a separate checkout. Report the revision, environment, expected result and what you observed. Draft any public message for approval.',
      `Открой ${page}. В MCP вызови portbridge_lab с task "${task.id}" или найди этот ID в https://akimfomin.github.io/PortBridge/data/lab.json. `
      + 'В исходном обсуждении проверь, нужен ли ещё прогон, и сверь точную версию. '
      + 'Используй синтетические данные в отдельной копии. Запиши версию, стенд, ожидаемый и фактический результат. Публичное сообщение подготовь для согласования.',
    );
    prompt.value = [intro, '', editorial(task, 'title'),
      t('Pinned versions', 'Точные версии'),
      ...list(task.revisions).map((revision) => `- ${editorial(revision, 'label')} ${revision.sha} ${revision.url}`),
      t('Steps', 'Шаги'),
      ...list(editorial(task, 'steps')).map((step, index) => `${index + 1}. ${step}`),
      `${t('Expected result', 'Ожидаемый результат')} — ${editorial(task, 'expected')}`,
      `${t('Reporting discussion', 'Обсуждение для отчёта')} — ${task.result_url}`,
    ].join('\n');
  }
  prompt.readOnly = true;
  prompt.hidden = true;
  prompt.setAttribute('aria-label', t('Agent instructions', 'Задание для агента'));
  const status = element('span', 'view-status');
  status.setAttribute('role', 'status');
  bindCopyText(copy, prompt, status, t('Copied. Paste into your agent chat.', 'Скопировано. Вставьте в чат с агентом.'));
  actions.append(copy, status);
  section.append(element('h2', '', t('Work with an agent', 'Работа с агентом')),
    element('p', '', t('Paste the instructions into your agent chat to get started.', 'Вставьте задание в чат с агентом, чтобы начать.')),
    actions, prompt);
  return section;
}

function labRequestURL(task, equipment) {
  const form = new URL(`${portbridgeRepository}/issues/new`);
  form.searchParams.set('template', 'test-request.yml');
  form.searchParams.set('title', 'Test request: ');
  if (!task) return form.href;
  if (task.status !== 'needs_run' || list(task.coverage).some((cell) => cell.equipment === equipment && cell.state === 'covered')
      || typeof task.id !== 'string' || !labTaskID.test(task.id)
      || !Object.hasOwn(labEquipment, equipment) || !list(task.equipment).includes(equipment)
      || typeof task.expected !== 'string' || !task.expected.trim()) return null;

  // The first test revision is the primary checkout. Controls stay in the task details.
  const pin = list(task.revisions)[0];
  const revision = githubURL(pin?.url);
  if (!revision || !/^[a-f0-9]{40}$/.test(pin?.sha)
      || !new URL(revision).pathname.endsWith(`/commit/${pin.sha}`)) return null;
  form.searchParams.set('title', `Test request: ${task.id} (${equipment})`);
  form.searchParams.set('task', task.id);
  form.searchParams.set('equipment', equipment);
  form.searchParams.set('revision', revision);
  form.searchParams.set('check', task.expected);
  return form.href;
}

function labRequestEntry() {
  const section = element('section', 'lab-agent');
  const actions = element('div', 'lab-agent-actions');
  const newRequest = githubLink(t('Request a test', 'Запросить тест'), labRequestURL());
  newRequest.classList.add('lab-primary');
  const queue = new URL(`${portbridgeRepository}/issues`);
  queue.searchParams.set('q', 'is:issue "Test request:" in:title');
  actions.append(newRequest, githubLink(t('View test requests', 'Смотреть запросы'), queue.href));
  section.append(element('h2', '', t('Find a tester', 'Найти тестировщика')),
    element('p', '', t('PortBridge matches a tester from public hardware reports and posts the invitation in your request after review.',
      'PortBridge подбирает тестировщика по публичным отчётам о стендах и после проверки оставляет приглашение в вашем запросе.')),
    actions, githubLink(t('How test requests work', 'Как работают запросы'), `${portbridgeRepository}/blob/main/docs/TEST-REQUESTS.md`));
  return section;
}

function labChecklist(title, items, ordered = false) {
  const section = element('section', 'lab-checklist');
  const rows = element(ordered ? 'ol' : 'ul');
  rows.append(...list(items).map((item) => element('li', '', item)));
  section.append(element('h3', '', title), rows);
  return section;
}

function labQueuePath(equipment, showAll) {
  const params = new URLSearchParams();
  if (Object.hasOwn(labEquipment, equipment)) params.set('equipment', equipment);
  if (showAll) params.set('status', 'all');
  return '#/lab' + (params.size ? '?' + params : '');
}

function labCompatibleEquipment(task, equipment) {
  const compatible = list(task.equipment).filter((kind) => Object.hasOwn(labEquipment, kind));
  let next = compatible.length === 1 ? compatible[0] : '';
  if (compatible.includes(equipment)) next = equipment;
  return next;
}

function labReport(task, returnPath, equipment) {
  const section = element('section', 'lab-agent');
  const actions = element('div', 'lab-agent-actions');
  const field = element('textarea');
  const page = portbridgePublicSite + labTaskPath(task.id);
  const cases = list(task.report_cases);
  const selected = labCompatibleEquipment(task, equipment);
  const reportHeader = cases.length ? [
    'PortBridge test report v1',
    'Task: ' + task.id,
    'Revisions: ' + list(task.revisions).map((revision) => revision.sha).join(' '),
    'Equipment: ' + selected,
    'Hardware: ',
    ...(selected === 'cpu' ? [] : ['PCI: ', 'Driver: ']),
    'OS: ',
    'Toolchain: ',
    'Opt-in: no',
    ...cases.map((name) => 'Case: ' + name + ' = '),
    '',
  ] : [];
  field.value = [
    ...reportHeader,
    `[PortBridge Test Lab](${page}) · ${editorial(task, 'title')}`,
    '',
    t('- Tested revision(s): ', '- Проверенные версии: '),
    t('- Environment and command: ', '- Стенд и команда запуска: '),
    t('- Expected: ', '- Ожидалось: ') + editorial(task, 'expected'),
    t('- Observed (include a failure or skip): ', '- Фактический результат (включая сбой или пропуск): '),
    t('- Limits or next step: ', '- Ограничения или следующий шаг: '),
  ].join('\n');
  field.readOnly = true;
  field.hidden = true;
  field.setAttribute('aria-label', t('Report template', 'Шаблон отчёта'));
  const status = element('span', 'view-status');
  status.setAttribute('role', 'status');
  const copy = element('button', 'retry', t('Copy result template', 'Копировать шаблон результата'));
  bindCopyText(copy, field, status, t('Copied. Fill in your result before sharing.',
    'Скопировано. Впишите свой результат перед публикацией.'));

  actions.append(copy, githubLink(t('Share result in the discussion', 'Оставить результат в обсуждении'), task.result_url),
    internalLink(t('Find another check', 'Выбрать другую проверку'), returnPath), status);
  section.append(element('h3', '', t('After the run', 'После прогона')));
  if (cases.length) {
    section.append(element('p', '', t('Fill in the fields and use pass, fail, or skip for each case. Choose yes under Opt-in only if you welcome other suitable tests.',
      'Заполните поля и укажите pass, fail или skip для каждой проверки. Выберите Opt-in yes, если готовы получать предложения о других подходящих тестах.')));
  }
  section.append(actions, field);
  return section;
}

function labReportsForReview(task) {
  return task.status === 'awaiting_review' && list(task.report_sync?.reports).length > 0;
}

function labReviewControls(task, report) {
  const discussion = list(task.report_sync.sources)[0]?.url;
  if (!discussion || !/^[a-f0-9]{64}$/.test(report.body_sha256 || '')) return '';
  const controls = element('details', 'lab-details lab-review');
  const decision = element('select');
  const label = element('label', 'filter-group', t('Decision', 'Решение'));
  const field = element('textarea');
  const status = element('span', 'view-status');
  const copy = element('button', 'retry', t('Copy decision template', 'Копировать шаблон решения'));
  const choices = [
    ['approve', t('Confirm report', 'Подтвердить отчёт')],
    ['revoke', t('Revoke confirmation', 'Отозвать подтверждение')],
  ];
  for (const [value, title] of choices) {
    const option = element('option', '', title);
    option.value = value;
    decision.append(option);
  }
  function updateTemplate() {
    field.value = [
      'PortBridge test review v1',
      'Task: ' + task.id,
      'Report: ' + report.url,
      'Body SHA-256: ' + report.body_sha256,
      'Decision: ' + decision.value,
    ].join('\n');
  }
  updateTemplate();
  decision.addEventListener('change', updateTemplate);
  field.readOnly = true;
  field.hidden = true;
  field.setAttribute('aria-label', t('Decision template', 'Шаблон решения'));
  status.setAttribute('role', 'status');
  label.append(decision);
  bindCopyText(copy, field, status, t('Copied. Post it in the review discussion.',
    'Скопировано. Опубликуйте в обсуждении для проверки.'));
  const actions = element('div', 'lab-agent-actions');
  actions.append(copy, githubLink(t('Open review discussion', 'Открыть обсуждение для проверки'), discussion), status);
  controls.append(element('summary', '', t('For the discussion owner', 'Для владельца обсуждения')),
    label, actions, field);
  return controls;
}

function labSyncedReports(task, focused) {
  const sync = task.report_sync;
  const section = element('section', 'lab-checklist');
  const checked = element('p', 'lab-checked', labReportStates[sync.state]);
  const date = sync.checked_at || sync.attempted_at;
  if (date) checked.append(activityTime(date));
  section.append(element('h3', '', t('Public test reports', 'Публичные отчёты о проверках')), checked);

  const reports = element('ul', 'lab-commits');
  for (const report of list(sync.reports)) {
    if (!report || !Object.hasOwn(labReportOutcomes, report.outcome)) continue;
    const row = element('li');
    const source = report.hardware || t('Open report', 'Открыть отчёт');
    row.append(githubLink(source, report.url), badge(report.outcome, labReportOutcomes));
    if (Object.hasOwn(labReportAuthority, report.authority)) row.append(badge(report.authority, labReportAuthority));
    if (report.author) row.append(element('span', '', `@${report.author}`));
    if (typeof report.revision === 'string' && /^[a-f0-9]{40}$/.test(report.revision)) {
      const revision = element('code', 'identifier', report.revision.slice(0, 12));
      revision.title = report.revision;
      row.append(revision);
    }
    if (report.reported_at) row.append(activityTime(report.reported_at));
    if (report.review?.decision === 'approve' || report.review?.decision === 'revoke') {
      const title = report.review.decision === 'approve'
        ? t('Confirmation by ', 'Подтверждение от ')
        : t('Confirmation revoked by ', 'Подтверждение отозвал ');
      row.append(githubLink(title + '@' + report.review.author, report.review.url));
    }
    if (focused) {
      const controls = labReviewControls(task, report);
      if (controls) row.append(controls);
    }
    reports.append(row);
  }
  if (reports.childElementCount) section.append(reports);
  else if (sync.state === 'fresh') section.append(element('p', '', t('No matching reports yet.', 'Подходящих отчётов пока нет.')));
  return section;
}

function labTask(task, focused = false, queueEquipment = '', showAll = false) {
  const card = element('article', 'card lab-task');
  const blocked = task.status === 'blocked';
  const reportsForReview = labReportsForReview(task);
  const status = element('div', 'meta-row lab-status');
  status.append(badge(task.status, labStatus), badge(task.evidence_stage, labEvidence), badge(task.adoption, labAdoption));
  const projects = element('div', 'meta-row');
  projects.append(...list(task.projects).map(projectPill));
  card.append(status, element('h2', '', editorial(task, 'title')), projects);
  const why = editorial(task, 'why');
  if (why) card.append(element('p', '', why));
  const setup = [...list(editorial(task, 'os')), ...list(editorial(task, 'requirements'))];
  if (setup.length) card.append(element('p', '', setup.join(' · ')));
  const evidence = editorial(task, 'evidence');
  if (evidence) card.append(element('p', 'lab-evidence', evidence));
  const coverage = list(task.coverage);
  if (coverage.length && (focused || task.coverage_policy === 'all')) {
    const cells = coverage.filter((cell) => Object.hasOwn(labEquipment, cell.equipment)
      && Object.hasOwn(labCoverageStates, cell.state)).map((cell) =>
      labEquipment[cell.equipment] + ' · ' + labCoverageStates[cell.state]);
    if (cells.length) card.append(labChecklist(t('Hardware coverage', 'Аппаратное покрытие'), cells));
  }
  if (task.report_sync && Object.hasOwn(labReportStates, task.report_sync.state)
      && (focused || list(task.report_sync.reports).length)) {
    card.append(labSyncedReports(task, focused));
  }

  const details = element('details', 'lab-details');
  details.open = focused && !reportsForReview;
  details.append(element('summary', '', t('Versions, steps and what to report', 'Версии, шаги и что указать в отчёте')));
  const versions = element('section', 'lab-checklist');
  const commits = element('ul', 'lab-commits');
  for (const revision of list(task.revisions)) {
    const entry = element('li');
    const sha = githubLink(revision.sha, revision.url);
    sha.classList.add('identifier');
    entry.append(element('span', '', editorial(revision, 'label')), sha);
    commits.append(entry);
  }
  if (commits.childElementCount) {
    versions.append(element('h3', '', t('Exact versions', 'Точные версии')), commits);
    details.append(versions);
  }
  details.append(labChecklist(t('Steps', 'Шаги'), editorial(task, 'steps'), true));
  const expected = element('section', 'lab-checklist');
  expected.append(element('h3', '', t('Expected result', 'Ожидаемый результат')), element('p', '', editorial(task, 'expected')));
  details.append(expected, labChecklist(t('Include in the report', 'Укажите в отчёте'), editorial(task, 'report')));

  const links = element('div', 'lab-links');
  if (!focused && typeof task.id === 'string' && labTaskID.test(task.id)) {
    const open = internalLink(t('Open this test', 'Открыть эту проверку'), labTaskPath(task.id, queueEquipment, showAll));
    open.setAttribute('aria-label', `${open.textContent} · ${editorial(task, 'title')}`);
    links.append(open);
  }
  if (!blocked) links.append(githubLink(reportsForReview ? t('View test procedure', 'Посмотреть порядок проверки')
    : t('Open instructions', 'Открыть инструкцию'), task.procedure_url));
  if (blocked || !focused || reportsForReview) {
    const discussion = blocked ? t('Report a confirmed public source', 'Сообщить публичный адрес')
      : reportsForReview ? t('Open reporting discussion', 'Открыть обсуждение с отчётами')
        : t('Share result in the discussion', 'Оставить результат в обсуждении');
    links.append(githubLink(discussion, task.result_url));
  }
  if (task.evidence_url) links.append(githubLink(t('Existing evidence', 'Что уже проверили'), task.evidence_url));
  if (task.source_check?.fetched_at) {
    const check = task.source_check;
    const note = element('p', 'lab-checked', t('Receiving source', 'Принимающая задача'));
    note.append(githubLink(sourceStates[check.status] || t('See current status', 'Смотреть статус'), check.url),
      activityTime(check.fetched_at));
    if (check.revision) note.append(element('code', 'identifier', check.revision.slice(0, 12)));
    card.append(note);
  }
  if (task.source_url && ![task.procedure_url, task.result_url, task.evidence_url].includes(task.source_url)) {
    links.append(githubLink(t('Coordination issue', 'Задача координации'), task.source_url));
  }
  const equipment = list(task.equipment);
  for (const kind of equipment) {
    const request = labRequestURL(task, kind);
    if (!request) continue;
    const label = equipment.length > 1 ? t(`Request a test · ${labEquipment[kind]}`, `Запросить тест · ${labEquipment[kind]}`)
      : t('Request a test', 'Запросить тест');
    links.append(githubLink(label, request));
  }
  card.append(links, details);
  if (focused) {
    const returnPath = labQueuePath(labCompatibleEquipment(task, queueEquipment), showAll);
    if (blocked || reportsForReview) links.append(internalLink(t('Find another check', 'Выбрать другую проверку'), returnPath));
    else card.append(labReport(task, returnPath, queueEquipment));
  }
  return card;
}

function drawLab(data, params) {
  const lab = element('div', 'lab');
  const selected = params.get('task');
  const all = list(data.tasks);
  viewStatus.textContent = '';
  if (selected !== null) {
    const task = labTaskID.test(selected) && all.find((entry) => entry.id === selected);
    const equipment = params.get('equipment') || '';
    const showAll = params.get('status') === 'all';
    const back = internalLink(t('Back to Test Lab', 'К очереди проверок'), labQueuePath(equipment, showAll));
    const bar = element('div', 'lab-bar');
    bar.append(back);
    lab.append(bar);
    if (task) {
      if (task.status !== 'blocked' && !labReportsForReview(task)) lab.append(labAgentEntry(task));
      lab.append(labTask(task, true, equipment, showAll));
    } else {
      lab.append(element('p', 'empty', t('This test is unavailable in the current queue.',
        'Этой проверки сейчас нет в очереди.')));
    }
    content.replaceChildren(lab);
    return;
  }
  const entrypoints = element('div', 'lab-entrypoints');
  entrypoints.append(labAgentEntry(), labRequestEntry());
  const bar = element('div', 'lab-bar');
  const group = element('div', 'filter-group');
  const equipment = element('select');
  equipment.id = 'lab-equipment';
  const label = element('label', '', t('Equipment available', 'Доступное оборудование'));
  label.htmlFor = equipment.id;
  equipment.append(new Option(t('All equipment', 'Любое оборудование'), ''));
  for (const kind of list(data.filters?.equipment)) {
    if (Object.hasOwn(labEquipment, kind)) equipment.append(new Option(labEquipment[kind], kind));
  }
  equipment.value = params.get('equipment') || '';
  if (equipment.selectedIndex === -1) equipment.selectedIndex = 0;
  group.append(label, equipment);
  const showAllLabel = element('label', 'lab-filter-toggle');
  const showAll = element('input');
  showAll.type = 'checkbox';
  showAll.checked = params.get('status') === 'all';
  showAllLabel.append(showAll, t('Show all statuses', 'Показать все статусы'));
  bar.append(group, showAllLabel);
  if (data.checked_at) {
    const checked = element('p', 'lab-checked', t('Task instructions reviewed', 'Инструкции к задачам сверены'));
    checked.append(activityTime(data.checked_at));
    bar.append(checked);
  }
  const count = element('p', 'view-status lab-count');
  count.setAttribute('role', 'status');
  const tasks = element('div', 'cards lab-tasks');
  function renderTasks() {
    const chosen = all.filter((task) => (showAll.checked || (task.status === 'needs_run'
      && !list(task.coverage).some((cell) => cell.equipment === equipment.value && cell.state === 'covered')))
      && (!equipment.value || list(task.equipment).includes(equipment.value)));
    count.textContent = t(`Tasks shown: ${numberFormat.format(chosen.length)}`, `Задач показано: ${numberFormat.format(chosen.length)}`);
    tasks.replaceChildren(...chosen.map((task) => labTask(task, false, equipment.value, showAll.checked)));
    if (!chosen.length) tasks.append(element('p', 'empty', showAll.checked
      ? t('No tests for this equipment.', 'Для этого оборудования пока нет проверок.')
      : t('There are no tests to take for this equipment. Show all statuses or request a test below.',
        'Для этого оборудования пока нет проверок, которые можно взять. Покажите все статусы или запросите тест ниже.')));
  }
  function updateFilters() {
    history.replaceState(null, '', labQueuePath(equipment.value, showAll.checked));
    updateLanguageLinks();
    renderTasks();
  }
  equipment.addEventListener('change', updateFilters);
  showAll.addEventListener('change', updateFilters);
  lab.append(bar, count, tasks, entrypoints);
  renderTasks();
  content.replaceChildren(lab);
}

async function loadView(current, focus = false, recovering = false, previousSnapshot = null) {
  request?.abort();
  request = new AbortController();
  const active = request;
  const [title, description] = labels[current.view];
  const isActivity = current.view === 'activity';
  const isLab = current.view === 'lab';
  const isSources = current.view === 'sources';
  const browse = Boolean(snapshotSite?.browse_index);
  const isMatches = current.view === 'matches';
  const onlySearch = isActivity || (isMatches && !browse);
  filters.hidden = current.id !== null || current.view === 'projects' || isLab;
  filters.classList.toggle('filters-only-search', onlySearch);
  byId('project-group').hidden = onlySearch;
  byId('status-group').hidden = onlySearch || isMatches;
  byId('stage-group').hidden = !browse || !isMatches;
  byId('kind-group').hidden = !browse || !isSources;
  if (isSources) {
    kindField.replaceChildren(new Option(t('Any source type', 'Любой тип источника'), ''),
      ...Object.entries(sourceKinds).map(([value, label]) => new Option(label, value)));
  }
  kindField.value = current.params.get('kind') || '';
  const states = isSources ? sourceStates : problemStates;
  statusField.replaceChildren(new Option(t('Any status', 'Любой статус'), ''),
    ...Object.entries(states).map(([value, label]) => new Option(label, value)));
  statusField.value = current.params.get('status') || '';
  stageField.value = current.params.get('stage') || '';
  byId('reset').hidden = isActivity;
  byId('search-submit').hidden = !isActivity;
  byId('readonly-mode').hidden = isActivity;
  refreshActivity.hidden = !isActivity && !snapshotSite;
  refreshActivity.disabled = true;
  summary.hidden = true;
  sectionDates(snapshotSite?.generated_at);
  heading.textContent = current.id ? current.id : title;
  byId('page-description').textContent = current.id ? '' : description;
  document.querySelectorAll('[data-route]').forEach((link) => {
    if (link.dataset.route === current.view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  content.setAttribute('aria-busy', 'true');
  viewStatus.textContent = t('Loading…', 'Загрузка…');
  try {
    const before = snapshotSite;
    if (!recovering && snapshotSite && await checkManifest(active.signal).catch(() => false)) {
      await loadProjects(active.signal).catch(() => {});
      await fetchJSON('/health', active.signal).then(setHealth).catch(() => {});
      if (!active.signal.aborted) return loadView(current, focus, true, before);
    }
    if (isActivity) {
      const result = await fetchJSON('/activity', active.signal);
      if (!active.signal.aborted) {
        showActivity(result);
        sectionDates(snapshotSite?.generated_at || result.as_of, latestChecked(list(result.projects).map((row) => row.last_success)));
      }
    } else if (isLab) {
      const result = await fetchJSON('/lab', active.signal);
      if (!active.signal.aborted) {
        drawLab(result, current.params);
        sectionDates(snapshotSite?.generated_at, latestChecked(list(result.tasks).flatMap((task) =>
          list(task.report_sync?.sources).map((source) => source.checked_at))));
      }
    } else if (current.view === 'projects') {
      const [, ecosystem] = await Promise.all([
        loadProjects(active.signal), fetchJSON('/ecosystem', active.signal).catch(() => null),
      ]);
      if (!active.signal.aborted) {
        drawProjects(ecosystem);
        sectionDates(snapshotSite?.generated_at, latestChecked([...list(ecosystem?.sources).map((source) => source.last_success),
          ...Array.from(projects.values(), (project) => project.last_success)]));
      }
    } else if (current.id) {
      const result = await fetchJSON(`/problems/${encodeURIComponent(current.id)}`, active.signal);
      if (!active.signal.aborted) {
        drawProblem(result.problem);
        sectionDates(snapshotSite?.generated_at, latestChecked(list(result.problem.solutions).flatMap((solution) =>
          list(solution.source_refs).map((source) => source.github?.fetched_at))));
      }
    } else if (isSources || (isMatches && snapshotSite?.browse_index)) {
      const result = await browsePublic(isMatches ? 'matches' : 'sources', current.params, active.signal);
      if (!active.signal.aborted) {
        if (isMatches) drawMatches(result.items, result, current);
        else drawSources(result, current);
        sectionDates(snapshotSite?.generated_at, latestChecked(Array.from(projects.values(), (project) => project.last_success)));
      }
    } else if (isMatches) {
      const params = new URLSearchParams({q: current.params.get('q') || ''});
      const result = await fetchJSON(`/matches?${params}`, active.signal);
      if (!active.signal.aborted) drawMatches(list(result.matches));
    } else {
      const params = new URLSearchParams(current.params);
      if (current.view === 'partial') params.set('partial', '1');
      const [result, activity, outreach] = await Promise.all([
        fetchJSON(`/problems?${params}`, active.signal),
        current.view === 'partial' ? fetchJSON('/activity', active.signal).catch(() => null) : null,
        current.view === 'partial' ? fetchJSON('/outreach', active.signal).catch(() => null) : null,
      ]);
      if (active.signal.aborted) return;
      const problems = list(result.problems);
      if (current.view === 'problems' && !current.params.size) summaryData = problems;
      if (current.view === 'problems' && summaryData) showSummary(summaryData);
      drawProblems(problems, current.view);
      if (current.view === 'partial') {
        showCurrentLeads(activity, current.params);
        showOutreach(outreach, problems);
      }
      sectionDates(snapshotSite?.generated_at, latestChecked(Array.from(projects.values(), (project) => project.last_success)));
    }
    if (focus && !active.signal.aborted) heading.focus({preventScroll: false});
    return !active.signal.aborted;
  } catch (err) {
    if (active.signal.aborted) return;
    const before = snapshotSite;
    if (!recovering && snapshotSite && await checkManifest(active.signal, true).catch(() => false)) {
      return loadView(current, focus, true, before);
    }
    if (previousSnapshot && !active.signal.aborted) {
      snapshotSite = previousSnapshot;
      summaryData = null;
      // A Pages edge can see the manifest before it sees every immutable file.
      // Restore the last usable generation and retry the update on the next tick.
      const [health] = await Promise.all([fetchJSON('/health', active.signal).catch(() => null),
        loadProjects(active.signal).catch(() => {})]);
      if (active.signal.aborted) return;
      if (health) setHealth(health);
      const rendered = await loadView(current, focus, true);
      if (rendered) viewStatus.append(element('span', 'snapshot-warning',
        t('New data is still publishing. Showing the previous snapshot.',
          'Новые данные ещё публикуются. Показан предыдущий снимок.')));
      return rendered;
    }
    if (active.signal.aborted) return;
    viewStatus.textContent = '';
    if (err.status === 404 && current.id) {
      stateScreen(t('Issue not found', 'Карточка не найдена'),
        t('Choose another issue from the catalog.', 'Откройте другую проблему из каталога.'));
    } else if (isActivity) {
      stateScreen(t('Activity is temporarily unavailable', 'Обновления временно недоступны'),
        t('Try again or choose Issue catalog in the menu.', 'Повторите попытку или откройте каталог проблем в меню.'), true);
    } else stateScreen(t('Could not load data', 'Не удалось загрузить данные'), retryAdvice, true);
  } finally {
    if (request === active) {
      content.setAttribute('aria-busy', 'false');
      refreshActivity.disabled = false;
    }
  }
}

async function loadProjects(signal) {
  const result = await fetchJSON('/projects', signal);
  if (signal?.aborted) return;
  projects.clear();
  const options = [new Option(t('All projects', 'Все проекты'), '')];
  list(result.projects).forEach((project) => {
    projects.set(project.slug, project);
    options.push(new Option(projectName(project.slug), project.slug));
  });
  projectField.replaceChildren(...options);
  projectField.value = route().params.get('project') || '';
}

function restoreFields(current) {
  searchField.value = (current.params.get('q') || '').slice(0, 200);
  projectField.value = current.params.get('project') || '';
  statusField.value = current.params.get('status') || '';
  stageField.value = current.params.get('stage') || '';
}

function filterHash(current) {
  const params = new URLSearchParams();
  if (searchField.value.trim()) params.set('q', searchField.value.trim());
  if (current.view !== 'activity') {
    if (projectField.value) params.set('project', projectField.value);
    if (current.view === 'matches') {
      if (stageField.value) params.set('stage', stageField.value);
    } else if (statusField.value) params.set('status', statusField.value);
    if (current.view === 'sources' && kindField.value) params.set('kind', kindField.value);
  }
  const suffix = params.size ? `?${params}` : '';
  const homeQuery = (params.get('q') || '').trim();
  if (current.view === 'activity' && /^PB-[0-9]{4,}$/i.test(homeQuery)) return urlFor(homeQuery.toUpperCase());
  const view = current.view === 'activity' ? (snapshotSite?.browse_index ? 'sources' : 'problems') : current.view;
  return `#/${view}${suffix}`;
}

function applyFilters() {
  clearTimeout(debounce);
  const current = route();
  if (current.view === 'activity') {
    if (searchField.value.trim()) window.location.hash = filterHash(current);
    else searchField.focus();
    return;
  }
  history.replaceState(null, '', filterHash(current));
  updateLanguageLinks();
  loadView(route());
}

applyPageLanguage();
updateLanguageLinks();
for (const [id, name] of Object.entries(problemStates)) statusField.add(new Option(name, id));
filters.addEventListener('submit', (event) => {
  event.preventDefault();
  applyFilters();
});
searchField.addEventListener('input', () => {
  clearTimeout(debounce);
  const current = route();
  if (current.view === 'activity') return;
  updateLanguageLinks(filterHash(current));
  debounce = setTimeout(applyFilters, 200);
});
async function refreshVisible(manual = false) {
  const active = request;
  if (!active || refreshActivity.disabled || document.hidden
      || (!manual && (content.contains(document.activeElement) || filters.contains(document.activeElement)))) return;
  if (manual) {
    refreshActivity.disabled = true;
    viewStatus.textContent = t('Checking for updates…', 'Проверяем обновления…');
  }
  try {
    if (snapshotSite) {
      const before = snapshotSite;
      const changed = await checkManifest(active.signal, true);
      if (request !== active) return;
      if (changed) {
        await Promise.all([loadProjects(active.signal).catch(() => {}),
          fetchJSON('/health', active.signal).then(setHealth).catch(() => {})]);
      }
      if (changed || manual) await loadView(route(), false, changed, changed ? before : null);
    } else if (route().view === 'activity') {
      const data = await fetchJSON('/activity', active.signal);
      if (request === active) showActivity(data, true);
    }
  } catch {
    if (manual && request === active) viewStatus.textContent =
      t('Could not check for updates. Try again.', 'Не удалось проверить обновления. Повторите попытку.');
  } finally {
    if (request === active) refreshActivity.disabled = false;
  }
}
refreshActivity.addEventListener('click', () => refreshVisible(true));
window.setInterval(refreshVisible, refreshPeriod);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && Date.now() - manifestChecked >= refreshPeriod) refreshVisible();
});
projectField.addEventListener('change', applyFilters);
statusField.addEventListener('change', applyFilters);
stageField.addEventListener('change', applyFilters);
kindField.addEventListener('change', applyFilters);
byId('reset').addEventListener('click', () => {
  searchField.value = '';
  projectField.value = '';
  statusField.value = '';
  stageField.value = '';
  kindField.value = '';
  applyFilters();
});
document.querySelector('.skip-link').addEventListener('click', (event) => {
  event.preventDefault();
  heading.focus();
});
window.addEventListener('hashchange', () => {
  clearTimeout(debounce);
  updateLanguageLinks();
  const current = route();
  restoreFields(current);
  loadView(current, true);
});

setHealth({status: 'pending'});
initializeData().then((health) => {
  setHealth(health);
  return loadProjects().catch(() => {});
}).then(() => {
  const current = route();
  restoreFields(current);
  loadView(current);
});
