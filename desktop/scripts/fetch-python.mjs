#!/usr/bin/env node
// Fetch a relocatable CPython (astral-sh/python-build-standalone) into vendor/python so the
// PACKAGED app needs no system python3. Idempotent; runs at package time (see package.json dist
// scripts). House-nothing note: this runs on the BUILD machine, not on the user's machine — the
// shipped app still only talks to 127.0.0.1.
//
// Bump: pick a newer release tag + CPython version from
// https://github.com/astral-sh/python-build-standalone/releases (use the `install_only` assets).
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const PBS_TAG = '20260610';     // python-build-standalone release tag
const PY_VERSION = '3.12.13';   // CPython version within that release

const HERE = dirname(fileURLToPath(import.meta.url));
const DESKTOP = join(HERE, '..');
const VENDOR = join(DESKTOP, 'vendor');
const DEST = join(VENDOR, 'python');

// node platform-arch -> python-build-standalone target triple
const TRIPLES = {
  'darwin-arm64': 'aarch64-apple-darwin',
  'darwin-x64': 'x86_64-apple-darwin',
  'win32-x64': 'x86_64-pc-windows-msvc',
  'linux-x64': 'x86_64-unknown-linux-gnu',
};

// Default = host. Override for cross-builds: `node scripts/fetch-python.mjs win32-x64`.
const target = process.argv[2] || `${process.platform}-${process.arch}`;
const triple = TRIPLES[target];
if (!triple) {
  console.error(`[fetch-python] unsupported target "${target}" (have: ${Object.keys(TRIPLES).join(', ')})`);
  process.exit(1);
}

const isWinTarget = target.startsWith('win32');
const pyBin = isWinTarget ? join(DEST, 'python.exe') : join(DEST, 'bin', 'python3');

if (existsSync(pyBin)) {
  console.log(`[fetch-python] already present: ${pyBin}`);
  process.exit(0);
}

const asset = `cpython-${PY_VERSION}+${PBS_TAG}-${triple}-install_only.tar.gz`;
const url = `https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${asset}`;
const tarball = join(VENDOR, asset);

mkdirSync(VENDOR, { recursive: true });
rmSync(DEST, { recursive: true, force: true });
console.log(`[fetch-python] downloading ${asset}`);
execFileSync('curl', ['-fSL', '--retry', '3', '-o', tarball, url], { stdio: 'inherit' });
console.log('[fetch-python] extracting -> vendor/python');
execFileSync('tar', ['-xzf', tarball, '-C', VENDOR], { stdio: 'inherit' }); // install_only extracts to ./python
rmSync(tarball, { force: true });
if (!existsSync(pyBin)) {
  console.error(`[fetch-python] expected ${pyBin} after extract — layout changed?`);
  process.exit(1);
}
console.log(`[fetch-python] ready: ${pyBin}`);
