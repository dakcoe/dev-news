import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const [page, testCase] = process.argv.slice(2);
const html = fs.readFileSync(page, 'utf8');
const DATA = JSON.parse(html.match(/const DATA = ([\s\S]*?);\n/)[1]);
const [a, b] = DATA;
assert.ok(a?.url && b?.url && a.url !== b.url);
const state = new Map();
const server = {saved: new Map([[a.url, a]]), read: new Set([a.url])};
let postStatus = 200;
const sent = [];
const ctx = vm.createContext({
  DATA, a, b, console, URLSearchParams,
  SAVE_KEY: 'saved', READ_KEY: 'read',
  read: new Set([a.url]), savedMap: new Map([[a.url, a]]),
  localStorage: {
    getItem: k => state.get(k) ?? null,
    setItem: (k, v) => state.set(k, String(v)), removeItem: k => state.delete(k),
  },
  setTimeout: () => 1, addEventListener() {},
  syncRenderAccount() {}, render() {}, renderList() {}, view: 'news',
  fetch: async (url, options = {}) => {
    if (url.endsWith('/me')) return {ok: true, json: async () => ({user: {id: 101}})};
    if (url.endsWith('/auth/logout')) return {ok: true};
    assert.ok(url.endsWith('/sync'), url);
    if (options.method !== 'POST') return {ok: true, json: async () => ({saved: [...server.saved.values()], read: [...server.read]})};
    const ops = JSON.parse(options.body).ops;
    sent.push(ops);
    if (postStatus === 200) for (const op of ops) {
      if (op.t === 'bm+') server.saved.set(op.url, op);
      if (op.t === 'bm-') server.saved.delete(op.url);
      if (op.t === 'rd') server.read.add(op.url);
      if (op.t === 'rd-') server.read.delete(op.url);
    }
    return {ok: postStatus === 200, status: postStatus};
  },
});
const run = source => vm.runInContext(source, ctx);
// 함수 복사본을 검사하면 템플릿에서 조건이 빠져도 통과하므로 생성된 구현을 읽는다.
run(html.slice(html.indexOf('function persist(){'), html.indexOf('/* 레일 맨 아래 계정 버튼.')));
run(html.slice(html.indexOf('async function syncLogout(){'), html.indexOf('/* 페이지를 열 때마다 한 번.')));
ctx.SWITCH_KEY = 'switch';
const initStart = html.indexOf('(async ()=>{', html.indexOf('/* 페이지를 열 때마다 한 번.'));
const init = html.slice(initStart, html.indexOf('})();', initStart) + 5);
const settle = () => new Promise(resolve => setImmediate(resolve));

if (testCase === 'failed_read' || testCase === 'failed_bookmark') {
  state.set('dev-news-synced', '1');
  state.set('dev-news-queue', JSON.stringify([{t: 'bm+', url: b.url, title: b.title}]));
  ctx.savedMap.set(b.url, b);
  postStatus = 503;
  await run(init);
  if (testCase === 'failed_read') run('read.delete(a.url); persistRead();');
  else run('savedMap.delete(a.url); persist();');
  const wanted = testCase === 'failed_read' ? 'rd-' : 'bm-';
  assert.ok(run('syncPending').some(op => op.t === wanted && op.url === a.url), '초기 전송 실패 뒤의 해제를 큐에 남긴다');
  postStatus = 200;
  await run('syncFlush()');
  assert.equal(testCase === 'failed_read' ? server.read.has(a.url) : server.saved.has(a.url), false);
  assert.equal(run('syncPending.length'), 0);
} else if (testCase === 'first_union') {
  server.saved = new Map([[b.url, b]]); server.read = new Set([b.url]);
  await run(init); await settle();
  assert.equal(ctx.savedMap.size, 2); assert.equal(ctx.read.size, 2);
  assert.ok(run('syncPending').every(op => op.t !== 'rd-' && op.t !== 'bm-'));
  await run('syncFlush()');
  assert.equal(server.saved.size, 2); assert.equal(server.read.size, 2);
} else if (testCase.startsWith('pull_')) {
  state.set('dev-news-synced', '1');
  run('syncUser = {id:101}; syncBase = {saved:new Set(savedMap.keys()), read:new Set(read)};');
  const fetch = ctx.fetch;
  const snapshot = {saved: [...server.saved.values()], read: [...server.read]};
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  ctx.fetch = async (url, options) => {
    if (!options?.method && url.endsWith('/sync')) {
      if (testCase === 'pull_json_edit') return {ok: true, json: () => gate};
      return await gate;
    }
    return fetch(url, options);
  };
  const pending = run('syncPull()');
  await settle();
  if (testCase === 'pull_logout') await run('syncLogout()');
  else {
    run('read.delete(a.url); persistRead();');
    await run('syncFlush()');
    assert.equal(server.read.has(a.url), false);
  }
  release(testCase === 'pull_json_edit' ? snapshot : {ok: true, json: async () => snapshot});
  await pending;
  assert.equal(ctx.read.has(a.url), false, '늦게 온 조회가 읽음 해제를 되돌리지 않는다');
  if (testCase === 'pull_logout') {
    assert.equal(ctx.savedMap.size, 0, '로그아웃 뒤 옛 계정의 보관함을 다시 넣지 않는다');
    assert.equal(run('syncUser'), null);
  }
} else if (testCase === 'init_reset') {
  let release;
  ctx.fetch = () => new Promise(resolve => { release = resolve; });
  const pending = run(init);
  run('syncEpoch++; savedMap.clear(); read.clear();');
  release({ok: true, json: async () => ({user: {id:101}})});
  await pending; await settle();
  assert.equal(run('syncUser'), null, '초기화 중 탈퇴가 끝나면 이전 계정 응답을 무시한다');
} else throw new Error(testCase);
console.log(testCase + ': 통과');
