import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const [page, kind, scenario] = process.argv.slice(2);
const html = fs.readFileSync(page, 'utf8');
// 함수 사본을 검사하면 템플릿의 분기가 빠져도 통과하므로 생성된 구현을 실행한다.
function extract(name) {
  const start = html.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} 없음`);
  let depth = 0;
  for (let i = html.indexOf('{', start); i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} 끝 없음`);
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const classList = {toggle() {}};
const buttons = ['api', 'skills'].map(v => ({dataset: {v}, classList}));
const requests = [], pending = [];
const ctx = vm.createContext({
  APIS: null, SKILLS: null, view: 'news', savedMap: new Map(),
  viewEl: {innerHTML: ''}, PAGE: 120, shown: 120, q: '',
  document: {querySelectorAll: () => buttons, querySelector: () => ({classList})},
  apiHTML: () => 'api', skillsHTML: () => 'skills', bindApi() {}, bindSkills() {},
  closePanels: () => false, popOverlay() {},
  fetch: url => {
    requests.push(url);
    return new Promise((resolve, reject) => pending.push({resolve, reject}));
  },
});
const run = source => vm.runInContext(source, ctx);
for (const name of ['ensureApis', 'ensureSkills', 'render']) run(extract(name));
const clickStart = html.lastIndexOf("document.querySelectorAll('.rb[data-v]').forEach(b=>b.onclick=()=>{");
assert.ok(clickStart >= 0);
run(html.slice(clickStart, html.indexOf('\n});', clickStart) + 4));

if (kind === 'schedule') {
  const frames = [], idle = [], timers = [], images = [];
  ctx.navigator = {connection: {saveData: scenario === 'save_data', effectiveType: scenario}};
  if (scenario === 'unknown') ctx.navigator = {};
  ctx.document.documentElement = {className: scenario === 'revisit' ? 'no-intro' : ''};
  ctx.requestAnimationFrame = f => frames.push(f);
  ctx.requestIdleCallback = (f, options) => { assert.equal(options.timeout, 2000); idle.push(f); };
  ctx.setTimeout = (f, ms) => { assert.equal(ms, 800); timers.push(f); };
  ctx.window = scenario === 'fallback' ? {} : {requestIdleCallback: ctx.requestIdleCallback};
  run(html.split('\n').find(line => line.startsWith('const ABOUT = ')) + '\nglobalThis.ABOUT = ABOUT;');
  ctx.Image = class {set src(url) { images.push(url); }};
  run(`(${extract('prewarm')})()`);
  assert.equal(requests.length, 0, '예약한 콜백을 실행하기 전에는 요청하지 않는다');
  if (['save_data', '2g', 'slow-2g'].includes(scenario)) {
    assert.equal(frames.length, 0);
    assert.equal(images.length, 0);
  } else {
    assert.equal(frames.length, 1); frames.shift()();
    assert.equal(requests.length, 0);
    const queue = scenario === 'fallback' ? timers : idle;
    assert.equal(queue.length, 1);
    if (scenario.endsWith('_before_idle')) {
      buttons[0].onclick();
      if (scenario === 'loaded_before_idle') {
        const payload = JSON.parse(fs.readFileSync(new URL('../../docs/data/apis.json', import.meta.url), 'utf8'));
        pending.shift().resolve({ok: true, json: async () => payload}); await settle();
      } else if (scenario === 'failed_before_idle') {
        pending.shift().resolve({ok: false}); await settle();
        assert.equal(ctx.APIS, 'fail');
      }
    }
    queue.shift()();
    assert.deepEqual(requests.sort(), ['data/apis.json', 'data/skills.json']);
    assert.equal(ctx.view, scenario.endsWith('_before_idle') ? 'api' : 'news');
    if (scenario === 'failed_before_idle') assert.equal(ctx.APIS, 'fail');
    assert.deepEqual(images, ctx.ABOUT.author_url ? [ctx.ABOUT.author_url.replace(/\/+$/, '') + '.png?size=208'] : []);
  }
} else {
  const key = kind === 'apis' ? 'APIS' : 'SKILLS';
  const view = kind === 'apis' ? 'api' : 'skills';
  const fn = kind === 'apis' ? 'ensureApis' : 'ensureSkills';
  const payload = JSON.parse(fs.readFileSync(new URL(`../../docs/data/${kind}.json`, import.meta.url), 'utf8'));
  const click = () => buttons.find(b => b.dataset.v === view).onclick();
  run(`${fn}(${scenario === 'ordinary_failure' ? '' : 'true'})`);
  if (['pending_success', 'pending_failure', 'ordinary_failure'].includes(scenario)) {
    click(); assert.equal(requests.length, 1, '로딩 중 탭을 눌러도 같은 요청을 늘리지 않는다');
  }
  if (['pending_success', 'hidden_success'].includes(scenario)) {
    pending.shift().resolve({ok: true, json: async () => payload});
  } else if (scenario === 'malformed_json') {
    pending.shift().resolve({ok: true, json: async () => { throw new SyntaxError('끊긴 응답'); }});
  } else pending.shift().resolve({ok: false});
  await settle();
  if (scenario === 'pending_failure') {
    assert.equal(requests.length, 2, '선택된 탭은 일반 요청으로 한 번 재시도한다');
    pending.shift().reject(new Error('offline')); await settle();
    assert.equal(ctx[key], 'fail'); assert.equal(requests.length, 2, '실패를 렌더할 때 무한 재시도하지 않는다');
    click(); assert.equal(requests.length, 3, '다시 누르면 fail을 풀고 요청한다');
    pending.shift().resolve({ok: true, json: async () => payload}); await settle();
    assert.deepEqual(ctx[key], payload);
  } else if (['failure_then_click', 'malformed_json'].includes(scenario)) {
    assert.equal(ctx[key], null); assert.equal(requests.length, 1);
    click(); assert.equal(requests.length, 2);
    pending.shift().resolve({ok: true, json: async () => payload}); await settle();
    assert.deepEqual(ctx[key], payload);
  } else if (scenario === 'ordinary_failure') {
    assert.equal(ctx[key], 'fail'); assert.equal(requests.length, 1);
  } else {
    assert.deepEqual(ctx[key], payload);
    assert.equal(requests.length, 1);
    assert.equal(ctx.view, scenario === 'hidden_success' ? 'news' : view);
    assert.equal(ctx.viewEl.innerHTML, scenario === 'hidden_success' ? '' : view);
  }
}
console.log(`${kind}/${scenario}: 통과`);
