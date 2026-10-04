import { build } from "esbuild";

await build({
  entryPoints: ["static/js/home.js"],
  bundle: true,
  minify: true,
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".js": "jsx" },
  jsxFactory: "React.createElement",
  jsxFragment: "React.Fragment",
  format: "iife",
  outfile: "static/js/home.compiled.js",
  logLevel: "info",
});
