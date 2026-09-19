/* dev-news 동기화 Worker.
 *
 * 정적 사이트(GitHub Pages)는 그대로 두고 이 Worker 만 api.dev-news.net 에 붙는다.
 * 하는 일은 둘이다 — 깃허브 OAuth 로 "누구인지" 확인하기, 그 사람의 보관함·읽음
 * 표시를 D1 에 보관하기.
 *
 * 깃허브 액세스 토큰은 브라우저로 내려보내지 않는다. 로그인 순간 Worker 안에서만
 * 쓰고 버리고, 브라우저에는 이 사이트에서만 통하는 세션 id 를 쿠키로 준다. 그래야
 * 사이트에 XSS 가 나도 깃허브 계정 권한이 새지 않는다.
 */

const SITE = 'https://dev-news.net';
const SESSION_DAYS = 30;
const STATE_MAX_AGE = 600;      // 로그인 왕복에 10분이면 넉넉하다
const MAX_OPS = 500;            // 한 번에 받는 변경분 개수 상한
const MAX_URL = 512;
const MAX_TEXT = 300;
const READ_KEEP = 1000;         // 프론트의 persistRead 와 같은 상한

const json = (body, status = 200, extra = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...extra },
  });

/* CORS. dev-news.net 과 api.dev-news.net 은 오리진이 다르므로 명시해야 하고,
   쿠키를 실어 보내려면 와일드카드(*)를 쓸 수 없다. */
function cors(req) {
  const origin = req.headers.get('Origin');
  if (origin !== SITE) return {};
  return {
    'Access-Control-Allow-Origin': SITE,
    'Access-Control-Allow-Credentials': 'true',
    'Vary': 'Origin',
  };
}

function randomToken() {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return [...b].map(x => x.toString(16).padStart(2, '0')).join('');
}

export function parseCookies(header) {
  const out = {};
  if (!header) return out;
  for (const part of header.split(';')) {
    const i = part.indexOf('=');
    if (i < 0) continue;
    out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

function setCookie(name, value, maxAge, path = '/') {
  // Domain 을 상위 도메인으로 둬야 dev-news.net 에서 보낸 요청에도 실린다.
  // 둘은 오리진이 다르지만 같은 사이트라 SameSite=Lax 로 통과한다.
  const bits = [
    `${name}=${encodeURIComponent(value)}`,
    `Max-Age=${maxAge}`,
    `Path=${path}`,
    'Domain=.dev-news.net',
    'HttpOnly', 'Secure', 'SameSite=Lax',
  ];
  return bits.join('; ');
}

const clearCookie = (name, path = '/') => setCookie(name, '', 0, path);

const now = () => Math.floor(Date.now() / 1000);

/* ---------------- 입력 검증 ---------------- */

/** 변경분 하나를 검사해 정규화한다. 못 쓰는 건 null 로 버린다. */
export function normalizeOp(op) {
  if (!op || typeof op !== 'object') return null;
  const url = typeof op.url === 'string' ? op.url.trim() : '';
  if (!url || url.length > MAX_URL) return null;
  if (!/^https?:\/\//i.test(url)) return null;

  const text = v => (typeof v === 'string' ? v.slice(0, MAX_TEXT) : '');

  if (op.t === 'bm+') {
    return {
      t: 'bm+', url,
      title: text(op.title) || url,
      month: text(op.month),
      kind: text(op.kind) || 'news',
      sub: text(op.sub),
      descr: text(op.desc),
    };
  }
  if (op.t === 'bm-') return { t: 'bm-', url };
  if (op.t === 'rd') {
    const at = Number.isFinite(op.at) ? Math.floor(op.at) : now();
    return { t: 'rd', url, at };
  }
  return null;
}

/* ---------------- 세션 ---------------- */

async function currentUser(req, env) {
  const sid = parseCookies(req.headers.get('Cookie')).sid;
  if (!sid) return null;
  const row = await env.DB
    .prepare('SELECT user_id, expires_at FROM session WHERE id = ?')
    .bind(sid).first();
  if (!row) return null;
  if (row.expires_at < now()) {
    await env.DB.prepare('DELETE FROM session WHERE id = ?').bind(sid).run();
    return null;
  }
  return row.user_id;
}

/* ---------------- 로그인 ---------------- */

function login(req, env) {
  const state = randomToken();
  const url = new URL('https://github.com/login/oauth/authorize');
  url.searchParams.set('client_id', env.GITHUB_CLIENT_ID);
  url.searchParams.set('scope', 'read:user');
  url.searchParams.set('state', state);
  url.searchParams.set('redirect_uri', `${new URL(req.url).origin}/auth/callback`);

  return new Response(null, {
    status: 302,
    headers: {
      Location: url.toString(),
      // state 를 쿠키에도 심어 두고 콜백에서 대조한다. 이게 없으면 공격자가 만든
      // 콜백 링크를 눌린 사람이 공격자 계정으로 로그인된다.
      'Set-Cookie': setCookie('oauth_state', state, STATE_MAX_AGE, '/auth'),
    },
  });
}

async function callback(req, env) {
  const url = new URL(req.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const saved = parseCookies(req.headers.get('Cookie')).oauth_state;

  if (!code || !state || !saved || state !== saved) {
    return json({ error: 'bad_state' }, 400, { 'Set-Cookie': clearCookie('oauth_state', '/auth') });
  }

  const tokenRes = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'content-type': 'application/json',
      'User-Agent': 'dev-news-sync',
    },
    body: JSON.stringify({
      client_id: env.GITHUB_CLIENT_ID,
      client_secret: env.GITHUB_CLIENT_SECRET,
      code,
      redirect_uri: `${url.origin}/auth/callback`,
    }),
  });
  const token = await tokenRes.json();
  if (!token.access_token) return json({ error: 'token_exchange_failed' }, 502);

  const ghRes = await fetch('https://api.github.com/user', {
    headers: {
      Authorization: `Bearer ${token.access_token}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'dev-news-sync',
    },
  });
  if (!ghRes.ok) return json({ error: 'github_user_failed' }, 502);
  const gh = await ghRes.json();
  if (!Number.isFinite(gh.id)) return json({ error: 'github_user_failed' }, 502);

  // 여기서 깃허브 토큰의 역할은 끝난다. 저장하지 않는다.
  const sid = randomToken();
  const t = now();
  await env.DB.batch([
    env.DB.prepare('INSERT OR IGNORE INTO app_user (id, created_at) VALUES (?, ?)').bind(gh.id, t),
    env.DB.prepare('INSERT INTO session (id, user_id, expires_at) VALUES (?, ?, ?)')
      .bind(sid, gh.id, t + SESSION_DAYS * 86400),
    env.DB.prepare('DELETE FROM session WHERE expires_at < ?').bind(t),
  ]);

  const headers = new Headers({ Location: SITE });
  headers.append('Set-Cookie', setCookie('sid', sid, SESSION_DAYS * 86400));
  headers.append('Set-Cookie', clearCookie('oauth_state', '/auth'));
  return new Response(null, { status: 302, headers });
}

async function logout(req, env) {
  const sid = parseCookies(req.headers.get('Cookie')).sid;
  if (sid) await env.DB.prepare('DELETE FROM session WHERE id = ?').bind(sid).run();
  return json({ ok: true }, 200, { ...cors(req), 'Set-Cookie': clearCookie('sid') });
}

/* ---------------- 동기화 ---------------- */

async function pull(req, env) {
  const uid = await currentUser(req, env);
  if (!uid) return json({ error: 'unauthorized' }, 401, cors(req));

  const [bm, rd] = await Promise.all([
    env.DB.prepare(
      'SELECT url, title, month, kind, sub, descr FROM bookmark WHERE user_id = ? ORDER BY created_at'
    ).bind(uid).all(),
    env.DB.prepare(
      'SELECT url FROM read_mark WHERE user_id = ? ORDER BY read_at DESC LIMIT ?'
    ).bind(uid, READ_KEEP).all(),
  ]);

  return json({
    saved: bm.results.map(r => ({
      url: r.url, title: r.title, month: r.month, kind: r.kind, sub: r.sub, desc: r.descr,
    })),
    read: rd.results.map(r => r.url),
  }, 200, cors(req));
}

async function push(req, env) {
  const uid = await currentUser(req, env);
  if (!uid) return json({ error: 'unauthorized' }, 401, cors(req));

  let body;
  try { body = await req.json(); } catch { return json({ error: 'bad_json' }, 400, cors(req)); }
  if (!Array.isArray(body?.ops)) return json({ error: 'bad_body' }, 400, cors(req));
  if (body.ops.length > MAX_OPS) return json({ error: 'too_many_ops' }, 413, cors(req));

  const ops = body.ops.map(normalizeOp).filter(Boolean);
  if (!ops.length) return json({ ok: true, applied: 0 }, 200, cors(req));

  const t = now();
  const stmts = ops.map(op => {
    if (op.t === 'bm+') {
      return env.DB.prepare(
        `INSERT INTO bookmark (user_id, url, title, month, kind, sub, descr, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(user_id, url) DO UPDATE SET
           title = excluded.title, month = excluded.month, kind = excluded.kind,
           sub = excluded.sub, descr = excluded.descr`
      ).bind(uid, op.url, op.title, op.month, op.kind, op.sub, op.descr, t);
    }
    if (op.t === 'bm-') {
      return env.DB.prepare('DELETE FROM bookmark WHERE user_id = ? AND url = ?').bind(uid, op.url);
    }
    return env.DB.prepare(
      `INSERT INTO read_mark (user_id, url, read_at) VALUES (?, ?, ?)
       ON CONFLICT(user_id, url) DO UPDATE SET read_at = excluded.read_at`
    ).bind(uid, op.url, op.at);
  });

  // 읽음 표시가 무한정 쌓이지 않게 사용자당 최근 READ_KEEP 건만 남긴다.
  stmts.push(env.DB.prepare(
    `DELETE FROM read_mark WHERE user_id = ?1 AND url NOT IN
       (SELECT url FROM read_mark WHERE user_id = ?1 ORDER BY read_at DESC LIMIT ?2)`
  ).bind(uid, READ_KEEP));

  await env.DB.batch(stmts);
  return json({ ok: true, applied: ops.length }, 200, cors(req));
}

/** 계정과 딸린 데이터를 전부 지운다. 개인정보 삭제 요구의 실행 경로다. */
async function erase(req, env) {
  const uid = await currentUser(req, env);
  if (!uid) return json({ error: 'unauthorized' }, 401, cors(req));
  await env.DB.batch([
    env.DB.prepare('DELETE FROM bookmark  WHERE user_id = ?').bind(uid),
    env.DB.prepare('DELETE FROM read_mark WHERE user_id = ?').bind(uid),
    env.DB.prepare('DELETE FROM session   WHERE user_id = ?').bind(uid),
    env.DB.prepare('DELETE FROM app_user  WHERE id = ?').bind(uid),
  ]);
  return json({ ok: true }, 200, { ...cors(req), 'Set-Cookie': clearCookie('sid') });
}

/* ---------------- 라우팅 ---------------- */

export default {
  async fetch(req, env) {
    const { pathname } = new URL(req.url);

    if (req.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          ...cors(req),
          'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
          'Access-Control-Allow-Headers': 'content-type',
          'Access-Control-Max-Age': '86400',
        },
      });
    }

    if (pathname === '/auth/login' && req.method === 'GET') return login(req, env);
    if (pathname === '/auth/callback' && req.method === 'GET') return callback(req, env);
    if (pathname === '/auth/logout' && req.method === 'POST') return logout(req, env);
    if (pathname === '/account' && req.method === 'DELETE') return erase(req, env);
    if (pathname === '/sync' && req.method === 'GET') return pull(req, env);
    if (pathname === '/sync' && req.method === 'POST') return push(req, env);
    if (pathname === '/me' && req.method === 'GET') {
      const uid = await currentUser(req, env);
      return json({ user: uid ? { id: uid } : null }, 200, cors(req));
    }

    return json({ error: 'not_found' }, 404, cors(req));
  },
};
