// 验证画布挂载前缀工具的运行时行为。
//
// 直接用真实源码：app-path.ts 除类型标注外是纯 JS，剥掉类型就能在 node 里跑，
// 这样测的是**真函数**而不是复制品——复制品会随源码漂移而失去意义。
const fs = require("node:fs");
const path = require("node:path");

const SRC = path.join(__dirname, "..", "infinite-canvas", "web", "src", "lib", "app-path.ts");
const raw = fs.readFileSync(SRC, "utf8");

// 剥掉类型标注，做成可执行的 CommonJS 模块
let code = raw
  .replace(/^import .*$/gm, "")
  .replace(/export const/g, "const")
  .replace(/export function/g, "function")
  .replace(/: string/g, "")
  .replace(/\): string \{/g, ") {")
  .replace(/\(pathname\)/g, "(pathname)");
code += "\nmodule.exports = { withBasePath, withoutBasePath, APP_BASE_PATH };\n";

function load(basePath) {
  const fn = new Function("process", "module", "exports", code);
  const mod = { exports: {} };
  fn({ env: { NEXT_PUBLIC_CANVAS_BASE_PATH: basePath } }, mod, mod.exports);
  return mod.exports;
}

const results = [];
function check(name, cond, detail) {
  results.push(`${cond ? "PASS" : "FAIL"}  ${name}${cond ? "" : "  -> " + detail}`);
}

// ---- 场景一：部署在子路径 ----
{
  const { withBasePath, withoutBasePath } = load("/canvas-app");

  check("应用内路径加前缀", withBasePath("/canvas") === "/canvas-app/canvas", withBasePath("/canvas"));
  check("带查询串也加前缀", withBasePath("/canvas/1?a=b") === "/canvas-app/canvas/1?a=b", withBasePath("/canvas/1?a=b"));
  check("根路径变 /canvas-app/", withBasePath("/") === "/canvas-app/", withBasePath("/"));
  check("幂等：已带前缀不重复", withBasePath("/canvas-app/canvas") === "/canvas-app/canvas", withBasePath("/canvas-app/canvas"));
  check("外链不动", withBasePath("https://example.com/x") === "https://example.com/x", withBasePath("https://example.com/x"));
  check("协议相对地址不动", withBasePath("//cdn.example.com/x") === "//cdn.example.com/x", withBasePath("//cdn.example.com/x"));
  check("空串不动", withBasePath("") === "", JSON.stringify(withBasePath("")));
  check("相对路径不动", withBasePath("icons/x.svg") === "icons/x.svg", withBasePath("icons/x.svg"));

  check("剥离前缀得应用内路径", withoutBasePath("/canvas-app/canvas") === "/canvas", withoutBasePath("/canvas-app/canvas"));
  check("前缀本身归一为根", withoutBasePath("/canvas-app") === "/", withoutBasePath("/canvas-app"));
  check("无前缀时原样返回", withoutBasePath("/canvas") === "/canvas", withoutBasePath("/canvas"));
}

// ---- 场景二：部署在根路径（必须完全退化，独立域名部署依赖它）----
{
  const { withBasePath, withoutBasePath } = load("");

  check("空配置下 withBasePath 恒等", withBasePath("/canvas") === "/canvas", withBasePath("/canvas"));
  check("空配置下根路径不变", withBasePath("/") === "/", withBasePath("/"));
  check("空配置下 withoutBasePath 恒等", withoutBasePath("/canvas") === "/canvas", withoutBasePath("/canvas"));
}

// ---- 场景三：配置带尾斜杠（部署脚本容易传成这样）----
{
  const { withBasePath } = load("/canvas-app/");
  check("尾斜杠被规整", withBasePath("/canvas") === "/canvas-app/canvas", withBasePath("/canvas"));
}

const failed = results.filter((r) => r.startsWith("FAIL"));
results.forEach((r) => console.log(r));
console.log(failed.length ? `\n${failed.length} 项失败` : "\n全部通过");
process.exit(failed.length ? 1 : 0);
