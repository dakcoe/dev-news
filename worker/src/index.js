/* dev-news 동기화 Worker (sync-across-devices).
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
const STATE_MAX_AGE = 1800;     // 로그인 왕복 제한. 10분은 짧았다 — 승인 화면을
                                // 띄워두고 딴 일을 하다 오면 그 사이 만료됐다
const MAX_OPS = 500;            // 한 번에 받는 변경분 개수 상한
const MAX_URL = 512;
const MAX_TEXT = 300;
const READ_KEEP = 1000;         // 프론트의 persistRead 와 같은 상한

/* 모든 응답에 no-store 를 붙인다. 여기 오가는 것은 전부 특정 사용자의 것이라
   어디에도 보관되면 안 된다 — 지금 Cloudflare 가 캐시하고 있지는 않지만, 중간
   프록시나 브라우저, 나중에 누군가 켤 캐시 규칙까지 막으려면 명시해야 한다. */
const noStore = { 'Cache-Control': 'no-store', 'Vary': 'Origin, Cookie' };

const json = (body, status = 200, extra = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...noStore, ...extra },
  });

/* CORS. dev-news.net 과 api.dev-news.net 은 오리진이 다르므로 명시해야 하고,
   쿠키를 실어 보내려면 와일드카드(*)를 쓸 수 없다. */
function cors(req) {
  const origin = req.headers.get('Origin');
  if (origin !== SITE) return {};
  return {
    'Access-Control-Allow-Origin': SITE,
    'Access-Control-Allow-Credentials': 'true',
    'Vary': 'Origin, Cookie',
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
  // Domain 을 적지 않는다. 그러면 쿠키가 api.dev-news.net 전용이 되고, 그래도
  // dev-news.net 페이지가 보내는 요청에는 실린다 — 목적지가 이 호스트이고 둘이
  // 같은 사이트라 SameSite=Lax 를 통과하기 때문이다. 상위 도메인으로 넓히면
  // 세션 토큰이 dev-news.net(= GitHub Pages 서버)에도 매 요청 전달되고, 나중에
  // 만들 다른 서브도메인에도 따라간다.
  const bits = [
    `${name}=${encodeURIComponent(value)}`,
    `Max-Age=${maxAge}`,
    `Path=${path}`,
    'HttpOnly', 'Secure', 'SameSite=Lax',
  ];
  return bits.join('; ');
}

const clearCookie = (name, path = '/') => setCookie(name, '', 0, path);

/* Domain=.dev-news.net 로 심겼던 예전 쿠키를 지운다. 안 지우면 같은 이름이 둘
   전송되고, 어느 쪽이 먼저 올지는 브라우저가 정해서 옛 값이 이길 수 있다. */
const clearLegacyCookie = (name, path = '/') =>
  `${name}=; Max-Age=0; Path=${path}; Domain=.dev-news.net; HttpOnly; Secure; SameSite=Lax`;

const now = () => Math.floor(Date.now() / 1000);

/* 깃허브에서 돌아오는 주소에 시각을 붙인다. GitHub Pages 가 index.html 에
   max-age=600 을 주기 때문에, 방금 고친 것이 최대 10분간 반영되지 않는다.
   주소가 달라지면 브라우저가 새로 받아 온다. */
const backTo = (extra = '') => `${SITE}/?v=${Date.now()}${extra}`;

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
  if (op.t === 'rd-') return { t: 'rd-', url };
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
  const here = new URL(req.url);
  const state = randomToken();
  const url = new URL('https://github.com/login/oauth/authorize');
  url.searchParams.set('client_id', env.GITHUB_CLIENT_ID);
  url.searchParams.set('scope', 'read:user');
  url.searchParams.set('state', state);
  url.searchParams.set('redirect_uri', `${here.origin}/auth/callback`);

  /* 로그아웃을 직접 누른 직후에만 계정 선택 화면을 띄운다. 깃허브 세션과 앱 승인은
     우리 로그아웃과 무관하게 남아 있어서, 그냥 두면 같은 계정으로 곧장 돌아온다.
     허용하는 값은 select_account 하나다 — 받은 문자열을 그대로 넘기지 않는다. */
  if (here.searchParams.get('prompt') === 'select_account') {
    url.searchParams.set('prompt', 'select_account');
  }

  const headers = new Headers({ Location: url.toString(), 'Cache-Control': 'no-store' });
  // state 를 쿠키에도 심어 두고 콜백에서 대조한다. 이게 없으면 공격자가 만든
  // 콜백 링크를 눌린 사람이 공격자 계정으로 로그인된다.
  headers.append('Set-Cookie', setCookie('oauth_state', state, STATE_MAX_AGE, '/auth'));
  headers.append('Set-Cookie', clearLegacyCookie('oauth_state', '/auth'));
  // 탈퇴는 깃허브를 한 번 더 거친다. 새로 받은 토큰으로 앱 승인을 취소해야
  // 다음 로그인이 동의 화면부터 다시 시작한다. 토큰은 여기서도 저장하지 않는다.
  headers.append('Set-Cookie',
    setCookie('oauth_intent', here.searchParams.get('intent') === 'delete' ? 'delete' : '',
              STATE_MAX_AGE, '/auth'));
  return new Response(null, { status: 302, headers });
}

/* 탈퇴를 시작해도 된다는 증표를 발급한다. 이 한 단계가 없으면 링크 한 줄로
   남의 계정을 지울 수 있다 — 깃허브 승인이 살아 있으면 클릭 한 번에 왕복이
   끝나기 때문이다. SameSite=Lax 라 다른 사이트에서 온 POST 에는 쿠키가 실리지
   않으므로, 이 요청은 우리 화면에서만 성공한다. */
async function prepareDelete(req, env) {
  const uid = await currentUser(req, env);
  if (!uid) return json({ error: 'unauthorized' }, 401, cors(req));
  const nonce = randomToken();
  const sid = parseCookies(req.headers.get('Cookie')).sid;
  await env.DB.prepare('UPDATE session SET del_nonce = ? WHERE id = ?').bind(nonce, sid).run();
  return json({ ok: true }, 200, { ...cors(req), 'Set-Cookie': setCookie('del_nonce', nonce, 600, '/') });
}

async function callback(req, env) {
  const url = new URL(req.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const saved = parseCookies(req.headers.get('Cookie')).oauth_state;

  if (!code || !state || !saved || state !== saved) {
    /* 대개는 공격이 아니라 제한시간이 지난 것이다 — 승인 화면을 띄워두고 딴 일을
       하다 온 경우. 한 번은 조용히 다시 걸어준다. 그래도 안 되면 JSON 대신 사람이
       읽을 수 있는 안내를 준다. 무한 왕복을 막으려고 한 번으로 제한한다. */
    const headers = new Headers({ 'Cache-Control': 'no-store' });
    headers.append('Set-Cookie', clearCookie('oauth_state', '/auth'));
    headers.append('Set-Cookie', clearLegacyCookie('oauth_state', '/auth'));
    if (url.searchParams.get('retried') !== '1') {
      headers.set('Location', `${url.origin}/auth/login?retried=1`);
      return new Response(null, { status: 302, headers });
    }
    headers.set('content-type', 'text/html; charset=utf-8');
    return new Response(
      '<!doctype html><meta charset="utf-8">'
      + '<title>로그인하지 못했습니다 — dev-news</title>'
      + '<div style="max-width:32em;margin:16vh auto;padding:0 24px;'
      + 'font:16px/1.7 -apple-system,BlinkMacSystemFont,\'Apple SD Gothic Neo\',sans-serif">'
      + '<h1 style="font-size:22px;margin:0 0 12px">로그인하지 못했습니다</h1>'
      + '<p style="color:#54545f;margin:0 0 20px">승인까지 시간이 너무 오래 걸렸거나 '
      + '창을 여러 개 띄운 상태였습니다. 다시 시도하면 대개 됩니다.</p>'
      + `<p><a href="${SITE}" style="color:#5b4fd0">dev-news 로 돌아가기</a></p></div>`,
      { status: 400, headers });
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

  const intent = parseCookies(req.headers.get('Cookie')).oauth_intent;
  if (intent === 'delete') return finishDelete(req, env, gh.id, token.access_token);

  // 여기서 깃허브 토큰의 역할은 끝난다. 저장하지 않는다.
  const sid = randomToken();
  const t = now();
  await env.DB.batch([
    env.DB.prepare('INSERT OR IGNORE INTO app_user (id, created_at) VALUES (?, ?)').bind(gh.id, t),
    env.DB.prepare('INSERT INTO session (id, user_id, expires_at) VALUES (?, ?, ?)')
      .bind(sid, gh.id, t + SESSION_DAYS * 86400),
    env.DB.prepare('DELETE FROM session WHERE expires_at < ?').bind(t),
  ]);

  const headers = new Headers({ Location: backTo(), 'Cache-Control': 'no-store' });
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
    // 읽음 해제. 이게 없으면 한 기기에서 해제해도 다른 기기는 계속 읽음으로 보고,
    // 다음 pull 이 서버 값을 씌워 해제한 기기에서도 되살아난다.
    if (op.t === 'rd-') {
      return env.DB.prepare('DELETE FROM read_mark WHERE user_id = ? AND url = ?').bind(uid, op.url);
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

/* 증표를 확인하고, 자료를 지우고, 깃허브 앱 승인까지 취소한다.
   순서가 중요하다 — 승인을 취소하면 토큰이 죽으므로 취소가 마지막이다. */
async function finishDelete(req, env, ghId, accessToken) {
  const cookies = parseCookies(req.headers.get('Cookie'));
  const row = cookies.sid
    ? await env.DB.prepare('SELECT user_id, del_nonce FROM session WHERE id = ?').bind(cookies.sid).first()
    : null;

  const headers = new Headers({ 'Cache-Control': 'no-store' });
  headers.append('Set-Cookie', clearCookie('oauth_state', '/auth'));
  headers.append('Set-Cookie', clearCookie('oauth_intent', '/auth'));
  headers.append('Set-Cookie', clearCookie('del_nonce'));

  // 우리 화면에서 확인했고, 다시 로그인한 계정이 그 계정과 같아야 한다
  const allowed = row && row.del_nonce && cookies.del_nonce === row.del_nonce
                  && row.user_id === ghId;
  if (!allowed) {
    headers.set('Location', backTo('&left=denied'));
    return new Response(null, { status: 302, headers });
  }

  await env.DB.batch([
    env.DB.prepare('DELETE FROM bookmark  WHERE user_id = ?').bind(ghId),
    env.DB.prepare('DELETE FROM read_mark WHERE user_id = ?').bind(ghId),
    env.DB.prepare('DELETE FROM session   WHERE user_id = ?').bind(ghId),
    env.DB.prepare('DELETE FROM app_user  WHERE id = ?').bind(ghId),
  ]);

  // 앱 승인 취소. 실패해도 자료는 이미 지웠으므로 탈퇴는 성립한다.
  let revoked = false;
  try {
    const r = await fetch(`https://api.github.com/applications/${env.GITHUB_CLIENT_ID}/grant`, {
      method: 'DELETE',
      headers: {
        Authorization: 'Basic ' + btoa(`${env.GITHUB_CLIENT_ID}:${env.GITHUB_CLIENT_SECRET}`),
        Accept: 'application/vnd.github+json',
        'content-type': 'application/json',
        'User-Agent': 'dev-news-sync',
      },
      body: JSON.stringify({ access_token: accessToken }),
    });
    revoked = r.status === 204;
  } catch (e) {}

  headers.set('Location', backTo(revoked ? '&left=1' : '&left=kept'));
  return new Response(null, { status: 302, headers });
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
    if (pathname === '/account/prepare' && req.method === 'POST') return prepareDelete(req, env);
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
