import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const [pagePath, dataDir, testCase] = process.argv.slice(2);
const html = fs.readFileSync(pagePath, 'utf8');
const constant = name => JSON.parse(html.match(new RegExp(`const ${name} = ([\\s\\S]*?);\\n`))[1]);
const all = constant('DATA');
const TAGS = JSON.parse(html.match(/const TAGS = ([\s\S]*?);/)[1]);
// 시간이 흘러 실제 기사가 기간 밖으로 밀려도 같은 회귀를 검증해야 한다.
const now = Math.max(...all.map(d => Date.parse(d.batch))) + 3600000;
const DATA = all.filter(d => Date.parse(d.batch) > now - 30 * 86400000);
const manifest = JSON.parse(fs.readFileSync(path.join(dataDir, 'search-index.json')));
const INDEX = manifest.months.flatMap(m => JSON.parse(fs.readFileSync(path.join(dataDir, `search-index-${m}.json`))));
const ctx = {
  DATA, INDEX, TAGS, view: 'news', sort: 'batch', days: 0, q: '', filter: 'all',
  tagSel: new Set(), read: new Set(), unreadOnly: false, GRAMS: new Map(),
  Date: class extends Date { static now() { return now; } },
};
vm.createContext(ctx);

// run_fn.mjs처럼 생성된 페이지의 함수를 사용해야 템플릿 수정 누락을 잡는다.
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
vm.runInContext(html.match(/const ALIAS=[\s\S]*?\]\];/)[0].replace('const ALIAS', 'globalThis.ALIAS'), ctx);
for (const name of ['inDays', 'sorted', 'tagLabel', 'qTokens', 'grams', 'tokHit', 'searchScore', 'docFields',
                    'visible', 'facetScope', 'archMatches', 'bind']) {
  vm.runInContext(extract(name), ctx);
}
const urls = items => Array.from(items, d => d.url).sort();

if (testCase === 'filters') {
  const recent = DATA.filter(d => Date.parse(d.batch) > now - 3 * 86400000);
  const sample = recent.find(d => d.tags.length >= 2);
  assert.ok(sample, '태그가 둘 이상인 최근 실제 기사가 필요하다');
  const chosen = sample.tags.slice(0, 2);
  const query = sample.title;
  const byDate = new Set(recent.map(d => d.url));
  const bySource = new Set(DATA.filter(d => d.src === sample.src).map(d => d.url));
  const byTags = new Set(DATA.filter(d => chosen.some(t => d.tags.includes(t))).map(d => d.url));
  // 검색어가 무엇에 걸리는지는 'search' 검사가 본다. 여기는 다른 조건과 겹칠 때만 본다.
  const toks = ctx.qTokens(query);
  const byQuery = new Set(DATA.filter(d => ctx.searchScore(toks, ctx.docFields(d)) > 0).map(d => d.url));
  assert.ok(byQuery.has(sample.url), '제목으로 검색하면 그 기사가 나와야 한다');
  ctx.days = 3;
  ctx.read = new Set([sample.url]);
  for (const search of ['', query]) for (const source of ['all', sample.src]) for (const tags of [[], chosen]) for (const unread of [false, true]) {
    Object.assign(ctx, {q: search, filter: source, tagSel: new Set(tags), unreadOnly: unread});
    for (const skip of [null, 'tag', 'src']) {
      const sets = [byDate];
      if (search) sets.push(byQuery);
      if (source !== 'all' && skip !== 'src') sets.push(bySource);
      if (tags.length && skip !== 'tag') sets.push(byTags);
      const expected = DATA.filter(d => sets.every(s => s.has(d.url)) && (!unread || d.url !== sample.url));
      const actual = skip ? ctx.facetScope(skip) : ctx.visible();
      assert.deepEqual(urls(actual), urls(expected), JSON.stringify({search, source, tags, unread, skip}));
    }
  }
} else if (testCase === 'sort') {
  for (const sort of ['batch', 'new', 'src']) {
    ctx.sort = sort;
    const result = ctx.visible();
    assert.deepEqual(urls(result), urls(DATA));
    for (let i = 1; i < result.length; i++) {
      const a = result[i - 1], b = result[i];
      if (sort === 'new') assert.ok(Date.parse(a.pub) >= Date.parse(b.pub));
      else {
        if (sort === 'batch') assert.ok(a.batch >= b.batch);
        else assert.ok(a.src.localeCompare(b.src) <= 0);
        if (sort === 'batch' ? a.batch === b.batch : a.src === b.src) assert.ok(a.score >= b.score);
      }
    }
  }
} else if (testCase === 'controls') {
  const nodes = {unread: {}, tagclear: {}};
  const dropdowns = [{dataset: {dd: 'sortsel', v: 'new'}}, {dataset: {dd: 'daysel', v: '7'}}];
  let renders = 0, persists = 0;
  Object.assign(ctx, {
    document: {getElementById: id => nodes[id]},
    viewEl: {querySelectorAll: selector => selector === '.dditem' ? dropdowns : []},
    initAds() {}, watchMore() {}, render() { renders++; }, persistTags() { persists++; },
    PAGE: 120, shown: 360, tagSel: new Set(['ai', 'llm']), filter: 'github',
    days: 3, unreadOnly: true, q: 'AI', sort: 'src',
  });
  ctx.bind();
  nodes.tagclear.onclick();
  assert.equal(ctx.tagSel.size, 0);
  assert.equal(ctx.filter, 'all');
  assert.equal(ctx.days, 3);
  assert.equal(ctx.unreadOnly, true);
  assert.equal(ctx.q, 'AI');
  assert.equal(ctx.sort, 'src');
  assert.equal(ctx.shown, 120);
  assert.equal(persists, 1);
  dropdowns[0].onclick({stopPropagation() {}});
  assert.equal(ctx.sort, 'new');
  dropdowns[1].onclick({stopPropagation() {}});
  assert.equal(ctx.days, 7);
  nodes.unread.onclick();
  assert.equal(ctx.unreadOnly, false);
  assert.equal(renders, 4);
} else if (testCase === 'archive') {
  const here = new Set(DATA.map(d => d.url));
  const sample = INDEX.find(e => !here.has(e.u) && !e.g?.length);
  assert.ok(sample, '태그 없는 실제 과거 기사가 필요하다');
  // 과거 무태그 기사를 태그 선택만으로 영영 숨기지 않는 기존 예외를 지킨다.
  Object.assign(ctx, {q: sample.t, tagSel: new Set(['ai'])});
  assert.ok(ctx.archMatches().some(e => e.u === sample.u));
  ctx.read.add(sample.u);
  ctx.unreadOnly = true;
  assert.ok(ctx.archMatches().every(e => e.u !== sample.u));
  ctx.unreadOnly = false;
  ctx.filter = Object.keys(constant('SRC')).find(s => s !== sample.s);
  assert.ok(ctx.archMatches().every(e => e.u !== sample.u));
  ctx.filter = 'all';
  ctx.days = 7;
  assert.ok(ctx.archMatches().every(e => e.u !== sample.u));
  ctx.days = 0;
  ctx.DATA = [...DATA, {url: sample.u}];
  assert.ok(ctx.archMatches().every(e => e.u !== sample.u));
} else if (testCase === 'search') {
  // 검색 의미를 고정된 기사로 본다. 실제 코퍼스는 회차마다 바뀐다.
  const d = (url, title, extra = {}) => ({url, title, snip: '', from: 'HN', tags: [], src: 'hackernews',
                                          batch: '2026-08-14T17:14:00+09:00', pub: '2026-08-14T08:00:00Z', ...extra});
  const docs = [
    d('wm-ing', 'AI 텍스트 워터마킹 작동 방식', {orig: 'How AI text watermarking works'}),
    d('wm-claude', 'Claude의 워터마크가 글쓰기를 왜곡하는 방식'),
    d('snip-only', 'EU AI 법 시행', {snip: 'Claude 출력에 워터마크가 들어간다', batch: '2026-08-20T00:00:00+09:00'}),
    d('download', '다운로드 속도 개선'),
  ];
  Object.assign(ctx, {DATA: docs, days: 0, tagSel: new Set(), filter: 'all', unreadOnly: false, read: new Set()});
  // vm 쪽 배열은 프로토타입이 달라 deepEqual 이 거부한다 — 이쪽 배열로 옮긴다
  const find = query => { ctx.q = query; return Array.from(ctx.visible(), x => x.url); };
  assert.ok(find('워터마크').includes('wm-ing'), '어미가 달라도 찾는다 (워터마크 → 워터마킹)');
  assert.ok(find('claude 워터마크').includes('wm-claude'), '낱말이 떨어져 있어도 찾는다');
  assert.ok(find('클로드 워터마크').includes('wm-claude'), '한글 표기로도 찾는다');
  assert.deepEqual(find('watermark'), ['wm-ing'], '원제로도 찾는다');
  assert.deepEqual(find('claude 러스트'), [], '낱말 하나라도 없으면 안 나온다');
  assert.ok(!find('클로드').includes('download'), '두 조각 중 하나만 겹치면 안 걸린다 (클로드 ≠ 다운로드)');
  const order = find('claude 워터마크');
  assert.ok(order.indexOf('wm-claude') < order.indexOf('snip-only'), '제목에 걸린 기사가 요약에만 걸린 것보다 위');
  // 아카이브 색인도 원제(o)와 요약 앞부분(x)을 본다
  Object.assign(ctx, {DATA: [], INDEX: [
    {t: 'AI 텍스트 워터마킹 작동 방식', o: 'How AI text watermarking works', u: 'a1', s: 'hackernews', g: [], d: '2026-08-14'},
    {t: 'EU AI 법 시행', x: '클로드 출력에 워터마크가', u: 'a2', s: 'rss', g: [], d: '2026-08-20'},
  ]});
  ctx.q = 'watermark';
  assert.deepEqual(Array.from(ctx.archMatches(), e => e.u), ['a1']);
  ctx.q = 'claude 워터마크';
  assert.deepEqual(Array.from(ctx.archMatches(), e => e.u), ['a2']);
} else {
  throw new Error(`알 수 없는 검사: ${testCase}`);
}
process.stdout.write(JSON.stringify({case: testCase}));
