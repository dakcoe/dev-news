/* 순수 함수만 검사한다. D1 과 fetch 가 걸린 경로는 `wrangler dev` 로 직접 확인한다.
 * 실행: node test.mjs
 */
import assert from 'node:assert/strict';
import { normalizeOp, parseCookies } from './src/index.js';

/* ---- parseCookies ---- */
assert.deepEqual(parseCookies(''), {});
assert.deepEqual(parseCookies(null), {});
assert.deepEqual(parseCookies('sid=abc'), { sid: 'abc' });
assert.deepEqual(parseCookies('sid=abc; oauth_state=xyz'), { sid: 'abc', oauth_state: 'xyz' });
// 값에 = 가 들어가도 첫 = 에서만 쪼갠다
assert.deepEqual(parseCookies('a=b=c'), { a: 'b=c' });
// 퍼센트 인코딩은 풀어준다
assert.deepEqual(parseCookies('k=%EA%B0%80'), { k: '가' });

/* ---- normalizeOp: 거부해야 하는 것 ---- */
assert.equal(normalizeOp(null), null);
assert.equal(normalizeOp({}), null);
assert.equal(normalizeOp({ t: 'bm+' }), null, 'url 없으면 거부');
assert.equal(normalizeOp({ t: 'bm+', url: '   ' }), null, '공백뿐이면 거부');
assert.equal(normalizeOp({ t: 'bm+', url: 'javascript:alert(1)' }), null, 'http(s) 아니면 거부');
assert.equal(normalizeOp({ t: 'bm+', url: 'ftp://x.com/a' }), null);
assert.equal(normalizeOp({ t: 'nope', url: 'https://example.com/a' }), null, '모르는 타입은 거부');
assert.equal(normalizeOp({ t: 'bm+', url: 'https://example.com/' + 'a'.repeat(600) }), null, '너무 길면 거부');

/* ---- normalizeOp: 통과와 정규화 ---- */
const add = normalizeOp({
  t: 'bm+', url: ' https://example.com/a ', title: '예시 제목',
  month: '2026-09', kind: 'news', sub: 'Hacker News', desc: '한 줄 설명',
});
assert.equal(add.url, 'https://example.com/a', '앞뒤 공백은 잘라낸다');
assert.equal(add.title, '예시 제목');
assert.equal(add.descr, '한 줄 설명', 'desc 는 descr 컬럼명으로 옮긴다');

// 제목이 비면 url 로 채운다 — 프론트 savedMap 이 하는 것과 같다
assert.equal(normalizeOp({ t: 'bm+', url: 'https://example.com/a' }).title, 'https://example.com/a');
assert.equal(normalizeOp({ t: 'bm+', url: 'https://example.com/a' }).kind, 'news', 'kind 기본값');

// 긴 텍스트는 자른다
assert.equal(normalizeOp({ t: 'bm+', url: 'https://example.com/a', title: 'ㄱ'.repeat(500) }).title.length, 300);

assert.deepEqual(normalizeOp({ t: 'bm-', url: 'https://example.com/a' }), { t: 'bm-', url: 'https://example.com/a' });

// 읽음 시각이 숫자가 아니면 서버 시각으로 대체한다
const rd = normalizeOp({ t: 'rd', url: 'https://example.com/a', at: 'nope' });
assert.equal(rd.t, 'rd');
assert.ok(Number.isInteger(rd.at) && rd.at > 1700000000, '서버 시각으로 대체');
assert.equal(normalizeOp({ t: 'rd', url: 'https://example.com/a', at: 1789806000.9 }).at, 1789806000, '소수는 버린다');

console.log('통과');
