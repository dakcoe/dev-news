/* 생성된 index.html 에서 함수 하나를 떼어 실제로 돌린다.
   문자열이 들어 있는지 보는 검사는 조건이 하나 빠져도 통과한다 —
   아카이브 검색에서 '안 읽음' 이 빠진 것을 그 방식으로는 못 잡았다.

   인자: <html 경로> <함수 이름> <전역 JSON>   결과: 반환값을 JSON 으로 stdout */
import fs from 'node:fs';
import vm from 'node:vm';

const [htmlPath, fnName, globalsJson] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, 'utf8');

// function 이름(...){ ... } 를 중괄호 짝을 세어 떼어 온다.
const start = html.indexOf(`function ${fnName}(`);
if (start < 0) throw new Error(`${fnName} 없음`);
let i = html.indexOf('{', start), depth = 0, end = -1;
for (let j = i; j < html.length; j++) {
  if (html[j] === '{') depth++;
  else if (html[j] === '}' && --depth === 0) { end = j + 1; break; }
}
const src = html.slice(start, end);

const ctx = { ...JSON.parse(globalsJson), console };
// Set 으로 받아야 하는 전역은 배열로 넘어온다.
for (const k of ['read', 'tagSel', 'savedKeys']) {
  if (Array.isArray(ctx[k])) ctx[k] = new Set(ctx[k]);
}
if (Array.isArray(ctx.DATA)) ctx.DATA = ctx.DATA.map(d => (typeof d === 'string' ? { url: d } : d));
vm.createContext(ctx);
vm.runInContext(`${src}; globalThis.__out = ${fnName}();`, ctx);
process.stdout.write(JSON.stringify(ctx.__out));
