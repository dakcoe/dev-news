import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import worker, { parseCookies } from './src/index.js';

// D1 의 SQL 을 그대로 실행해야 조건식이 빠진 쓰기나 잘못된 바인딩도 잡힌다.
const schema = readFileSync(new URL('./schema.sql', import.meta.url), 'utf8');
const articleDir = new URL('../docs/data/articles/', import.meta.url);
const articles = [...new Map(readdirSync(articleDir).filter(p => p.endsWith('.json'))
  .flatMap(p => JSON.parse(readFileSync(new URL(p, articleDir), 'utf8')))
  .map(a => [a.url, a])).values()];
assert.ok(articles.length > 1000, '읽음 보관 상한을 실제 기사로 검증한다');
const article = articles[0], other = articles[1];
const at = () => Math.floor(Date.now() / 1000);

function fixture() {
  const db = new DatabaseSync(':memory:');
  db.exec(schema);
  const env = {
    GITHUB_CLIENT_ID: 'test-client', GITHUB_CLIENT_SECRET: 'test-secret',
    DB: {
      prepare(sql) {
        return { bind(...args) {
          const stmt = db.prepare(sql);
          return {
            first: async () => stmt.get(...args) || null,
            all: async () => ({ results: stmt.all(...args) }),
            run: async () => stmt.run(...args),
            execute: () => ({ results: stmt.all(...args) }),
          };
        } };
      },
      async batch(stmts) {
        db.exec('BEGIN');
        try {
          const result = stmts.map(s => s.execute());
          db.exec('COMMIT');
          return result;
        } catch (e) { db.exec('ROLLBACK'); throw e; }
      },
    },
  };
  const addUser = (uid, sid) => {
    db.prepare('INSERT INTO app_user VALUES (?, ?)').run(uid, at());
    db.prepare('INSERT INTO session VALUES (?, ?, ?, NULL)').run(sid, uid, at() + 3600);
    db.prepare('INSERT INTO bookmark (user_id,url,title,created_at) VALUES (?,?,?,?)')
      .run(uid, article.url, article.ko_title || article.title, at());
    db.prepare('INSERT INTO read_mark VALUES (?,?,?)').run(uid, article.url, at());
  };
  addUser(101, 'first'); addUser(202, 'unrelated');
  db.prepare('INSERT INTO session VALUES (?, ?, ?, NULL)').run('second-device', 101, at() + 3600);
  const request = (path, method = 'GET', cookie = 'sid=first', body) => worker.fetch(
    new Request('https://api.dev-news.net' + path, {
      method, headers: { Cookie: cookie, Origin: 'https://dev-news.net' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }), env);
  const count = (table, uid = 101) => db.prepare(`SELECT count(*) AS n FROM ${table} WHERE ${table === 'app_user' ? 'id' : 'user_id'} = ?`).get(uid).n;
  const deleted = () => {
    for (const table of ['app_user', 'session', 'bookmark', 'read_mark']) {
      assert.equal(count(table), 0, `${table}: 탈퇴한 계정만 삭제`);
      assert.equal(count(table, 202), 1, `${table}: 다른 계정 유지`);
    }
  };
  const prepare = async () => {
    const res = await request('/account/prepare', 'POST');
    assert.equal(res.status, 200);
    const nonce = parseCookies(res.headers.getSetCookie()[0].split(';')[0]).del_nonce;
    assert.equal(db.prepare('SELECT del_nonce FROM session WHERE id = ?').get('first').del_nonce, nonce);
    return `sid=first; oauth_state=state; oauth_intent=delete; del_nonce=${nonce}`;
  };
  return { db, env, addUser, request, count, deleted, prepare };
}

const originalFetch = globalThis.fetch;
let githubId = 101, revokeStatus = 204, revocations = 0;
// 네트워크는 한 번도 나가지 않는다. OAuth 응답만 대체하고 Worker 라우팅·SQL 은 실제 실행한다.
globalThis.fetch = async url => {
  if (url === 'https://github.com/login/oauth/access_token') return Response.json({ access_token: 'test-token' });
  if (url === 'https://api.github.com/user') return Response.json({ id: githubId });
  if (url === 'https://api.github.com/applications/test-client/grant') {
    revocations++;
    return new Response(null, { status: revokeStatus });
  }
  throw new Error('허용하지 않은 외부 요청: ' + url);
};
const callbackPath = '/auth/callback?code=test-code&state=state';
try {
  for (const failure of ['nonce-missing', 'nonce-wrong', 'different-account']) {
    const f = fixture();
    let cookie = await f.prepare();
    if (failure === 'nonce-missing') cookie = cookie.replace(/; del_nonce=.*/, '');
    if (failure === 'nonce-wrong') cookie = cookie.replace(/del_nonce=.*/, 'del_nonce=wrong');
    githubId = failure === 'different-account' ? 202 : 101;
    const before = revocations;
    const res = await f.request(callbackPath, 'GET', cookie);
    assert.equal(new URL(res.headers.get('Location')).searchParams.get('left'), 'denied');
    assert.equal(f.count('bookmark'), 1); assert.equal(f.count('session'), 2);
    assert.equal(revocations, before, '거부한 탈퇴는 GitHub 승인도 취소하지 않는다');
    f.db.close();
  }
  githubId = 101;
  for (const status of [204, 503]) {
    const f = fixture(); revokeStatus = status;
    const res = await f.request(callbackPath, 'GET', await f.prepare());
    assert.equal(new URL(res.headers.get('Location')).searchParams.get('left'), status === 204 ? '1' : 'kept');
    f.deleted(); f.db.close();
  }
  revokeStatus = 204;
  {
    const f = fixture();
    for (const path of ['/account/prepare', '/account']) {
      assert.equal((await f.request(path, path.endsWith('prepare') ? 'POST' : 'DELETE', '')).status, 401);
    }
    assert.equal(f.count('bookmark'), 1);
    assert.equal((await f.request('/account', 'DELETE')).status, 200);
    f.deleted(); f.db.close();
  }
  for (const exit of ['erase', 'oauth', 'logout', 'expired', 'rejoined']) {
    const f = fixture();
    const cookie = exit === 'oauth' ? await f.prepare() : null;
    let release, began;
    const started = new Promise(resolve => { began = resolve; });
    const req = new Request('https://api.dev-news.net/sync', { method: 'POST', headers: { Cookie: 'sid=first' } });
    req.json = async () => { began(); return await new Promise(resolve => { release = resolve; }); };
    const pending = worker.fetch(req, f.env);
    await started;
    if (exit === 'oauth') await f.request(callbackPath, 'GET', cookie);
    else if (exit === 'logout') await f.request('/auth/logout', 'POST');
    else if (exit === 'expired') f.db.prepare('UPDATE session SET expires_at = ? WHERE id = ?').run(at() - 1, 'first');
    else await f.request('/account', 'DELETE');
    if (exit === 'rejoined') {
      f.addUser(101, 'new-session');
      // 옛 요청의 정리 DELETE 도 막아야 재가입 직후의 새 읽음 기록을 자르지 않는다.
      const insert = f.db.prepare('INSERT OR IGNORE INTO read_mark VALUES (?,?,?)');
      articles.slice(0, 1001).forEach(a => insert.run(101, a.url, at()));
    }
    const savedBefore = f.db.prepare('SELECT * FROM bookmark ORDER BY user_id,url').all();
    const readBefore = f.db.prepare('SELECT * FROM read_mark ORDER BY user_id,url').all();
    release({ ops: [
      { t: 'bm+', url: other.url, title: other.title }, { t: 'rd', url: other.url, at: at() },
      { t: 'bm-', url: article.url }, { t: 'rd-', url: article.url },
    ] });
    assert.equal((await pending).status, 401, `${exit}: 옛 세션 쓰기를 성공 처리하지 않는다`);
    assert.deepEqual(f.db.prepare('SELECT * FROM bookmark ORDER BY user_id,url').all(), savedBefore, exit);
    assert.deepEqual(f.db.prepare('SELECT * FROM read_mark ORDER BY user_id,url').all(), readBefore, exit);
    f.db.close();
  }
  {
    const f = fixture();
    const res = await f.request('/sync', 'POST', 'sid=first', { ops: [
      { t: 'bm-', url: article.url }, { t: 'rd-', url: article.url },
      { t: 'bm+', url: other.url, title: other.title }, { t: 'rd', url: other.url, at: at() },
    ] });
    assert.deepEqual(await res.json(), { ok: true, applied: 4 });
    const pulled = await (await f.request('/sync')).json();
    assert.deepEqual(pulled.saved.map(a => a.url), [other.url]);
    assert.deepEqual(pulled.read, [other.url]);
    f.db.close();
  }
} finally { globalThis.fetch = originalFetch; }
console.log('계정 삭제·옛 세션 쓰기 경합 통과');
