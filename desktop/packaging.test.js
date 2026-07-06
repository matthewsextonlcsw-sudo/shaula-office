// packaging.test.js — the installer may not ship a broken require graph.
//
// v0.1.0 shipped with main.js requiring ./model-util while build.files listed
// only main/preload/firstrun — the packaged app crashed on launch with
// "Cannot find module './model-util'" (found by actually opening the DMG a
// user downloads; unit tests can't see electron-builder config, so this test
// pins the config itself). Every local `require('./x')` in an entry file must
// be covered by build.files, and every listed file must exist.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "package.json"), "utf8"));
const files = pkg.build.files;

const localRequires = (src) => {
  const out = new Set();
  const re = /require\(\s*["']\.\/([A-Za-z0-9_./-]+)["']\s*\)/g;
  let m;
  while ((m = re.exec(src))) out.add(m[1].endsWith(".js") ? m[1] : m[1] + ".js");
  return [...out];
};

test("every local require in packaged entry files is in build.files", () => {
  for (const entry of ["main.js", "preload.js"]) {
    const src = fs.readFileSync(path.join(__dirname, entry), "utf8");
    for (const dep of localRequires(src)) {
      assert.ok(
        files.includes(dep),
        `${entry} requires ./${dep} but build.files does not package it — the app would crash on launch`
      );
    }
  }
});

test("every build.files entry exists on disk", () => {
  for (const f of files) {
    assert.ok(fs.existsSync(path.join(__dirname, f)), `build.files lists missing file: ${f}`);
  }
});
