// ontocraft-check 브라우저 실행기(Web Worker). 파일은 브라우저 밖으로 나가지 않습니다.
// 쓰는 쪽: new Worker("ontocraft-check-worker.js")
//   postMessage({ontology, data, shapes, registry, wheel, domains, disable, group_over})
//   → 진행 중 {stage: "running"}, 끝나면 {ok: true, json, html} 또는 {ok: false, error}
// ontology·data·shapes 는 파일 내용(문자열)과 이름 {name, text}, registry 는 {파일이름: 내용} 객체입니다.
//
// 0.3.0: 패키지 이름이 ontocheck 에서 ontocraft-check(import ontocraft_check)로 바뀌었습니다.
//   wheel 은 ontocraft_check-0.3.0-py3-none-any.whl 이고, 0.2 이하의 ontocheck wheel 은 이 worker 로 돌지 않습니다.
//   메시지 형식은 0.2.0 과 같습니다. registry 를 주지 않으면 등록부 대조를 하지 않습니다.
//   registry 에 문자열 "builtin" 을 주면 wheel 에 든 공개 분야 사본과 대조합니다(등록부 파일을 따로 보내지 않아도 됨).
//
// 0.2.0 에서 바뀐 메시지 형식(홈페이지가 이 worker 를 그대로 씁니다):
// - 입력에 선택 필드 세 개를 더했습니다. 빠지면 0.1 과 같게 동작하므로 0.1 형식의 메시지도 그대로 받습니다.
//   domains: 등록부 분야 id 배열(예: ["maritime", "maint"]). 없거나 빈 배열이면 모든 분야를 봅니다.
//            분야 id 는 등록부 파일의 domain.id 입니다(demo.html 처럼 registry 파일을 JSON.parse 해서 읽습니다).
//   disable: 끌 규칙 id 배열(예: ["P13"]). 없으면 끄지 않습니다.
//   group_over: 같은 규칙 항목을 묶는 기준 수. 없거나 null 이면 10, 0 이면 묶지 않습니다.
// - 출력 형식 {ok, json, html} 은 같습니다. json 안에 options(domains, disabled, disabled_counts,
//   unknown_disabled, group_over)와 grouped(묶은 규칙 요약)가 늘었고, findings 는 묶지 않은 그대로입니다.
//   등록부 항목 detail 에 domain_name, confidence("높음"|"낮음")가 늘었고, 고르지 않은 분야와만 맞은 것은 rule "REG02" 입니다.
// - 새 필드(domains, disable, group_over)를 쓰려면 wheel 이 0.2.0 이상이어야 합니다. 0.2 이전 화면과의 호환을 위해 값을 준 선택지만 run() 에 넘깁니다.
// 버전은 이 저장소의 uv.lock 과 맞춥니다. 바꾸면 이 줄과 홈페이지에 올린 wheel 을 함께 바꿉니다.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const PINS = ["rdflib==7.6.0", "owlrl==7.6.2", "pyshacl==0.40.1"];
importScripts(PYODIDE + "pyodide.js");
let ready = null;
async function boot(wheel) {
  const py = await loadPyodide({ indexURL: PYODIDE });
  await py.loadPackage("micropip");
  await py.pyimport("micropip").install(PINS.concat([wheel]));
  return py;
}
const ids = (v) => (Array.isArray(v) ? v.map(String).filter((x) => x) : []);
self.onmessage = async (e) => {
  const m = e.data;
  try {
    if (!ready) ready = boot(m.wheel);
    const py = await ready;
    self.postMessage({ stage: "running" });
    const fs = py.FS;
    try { fs.mkdir("/work"); } catch (_) {}
    const put = (f, p) => { if (!f) return null; const path = "/work/" + p + "-" + f.name.replace(/[^\w.-]/g, "_"); fs.writeFile(path, f.text); return path; };
    const o = put(m.ontology, "o"), d = put(m.data, "d"), s = put(m.shapes, "s");
    let reg = null;
    if (m.registry === "builtin") {
      reg = "builtin";
    } else if (m.registry) {
      // 실행마다 폴더를 비웁니다. 지난 실행의 등록부 파일이 남아 섞이지 않게 합니다.
      reg = "/work/registry";
      try { fs.mkdir(reg); } catch (_) {}
      for (const name of fs.readdir(reg)) if (name !== "." && name !== "..") fs.unlink(reg + "/" + name);
      for (const [k, v] of Object.entries(m.registry)) fs.writeFile(reg + "/" + k.replace(/[^\w.-]/g, "_"), v);
    }
    const groupOver = Number.isInteger(m.group_over) && m.group_over >= 0 ? m.group_over : null;
    py.globals.set("args", py.toPy({ o, d, s, reg, domains: ids(m.domains), disable: ids(m.disable), group_over: groupOver }));
    const out = py.runPython(`
from ontocraft_check.runner import run
from ontocraft_check.render import render
# 값을 준 선택지만 넘깁니다. 그래서 새 필드를 쓰지 않는 화면도 그대로 돕니다(배포 순서가 엇갈려도 깨지지 않게).
kw = {k: args[k] for k in ("domains", "disable", "group_over") if args[k] is not None and args[k] != []}  # group_over=0(묶지 않음)도 넘김
r = run(args["o"], data=args["d"], shapes=args["s"], registry_dir=args["reg"], **kw)
[render(r, "json"), render(r, "html")]
`).toJs();
    self.postMessage({ ok: true, json: out[0], html: out[1] });
  } catch (err) {
    self.postMessage({ ok: false, error: String(err) });
  }
};
