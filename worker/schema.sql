-- dev-news 동기화용 D1 스키마.
-- 적용: wrangler d1 execute dev-news-sync --remote --file=schema.sql

-- 깃허브 숫자 id 만 둔다. 이름·이메일·아바타는 화면에 쓰지 않으므로 저장하지 않는다.
CREATE TABLE IF NOT EXISTS app_user (
  id         INTEGER PRIMARY KEY,
  created_at INTEGER NOT NULL
);

-- 깃허브 토큰은 저장하지 않는다. 로그인 순간에만 쓰고 버린다.
CREATE TABLE IF NOT EXISTS session (
  id         TEXT    PRIMARY KEY,
  user_id    INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS session_expires ON session(expires_at);

-- 보관함은 스냅샷이다. 기사가 30일 창 밖으로 밀려나도 제목이 남아야 한다
-- (프론트의 savedMap 이 같은 이유로 제목·월을 함께 들고 있다).
CREATE TABLE IF NOT EXISTS bookmark (
  user_id    INTEGER NOT NULL,
  url        TEXT    NOT NULL,
  title      TEXT    NOT NULL DEFAULT '',
  month      TEXT    NOT NULL DEFAULT '',
  kind       TEXT    NOT NULL DEFAULT 'news',
  sub        TEXT    NOT NULL DEFAULT '',
  descr      TEXT    NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, url)
);

-- 읽음 표시는 url 만 있으면 된다. 프론트와 같게 사용자당 최근 1000건으로 자른다.
CREATE TABLE IF NOT EXISTS read_mark (
  user_id INTEGER NOT NULL,
  url     TEXT    NOT NULL,
  read_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, url)
);
CREATE INDEX IF NOT EXISTS read_recent ON read_mark(user_id, read_at);
