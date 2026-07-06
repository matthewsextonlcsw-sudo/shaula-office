'use strict';
// Unit tests for the pure model helpers. Run: node --test  (zero deps, stdlib node:test).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { modelInstalled, pullPercent, MODELS, DEFAULT_MODEL_KEY, modelById, bundledPythonRelPath } = require('../model-util');

const tags = (...names) => ({ models: names.map((n) => ({ name: n })) });

test('modelInstalled: exact tag match', () => {
  assert.equal(modelInstalled(tags('gemma3:4b', 'gemma3:1b'), 'gemma3:4b'), true);
});

test('modelInstalled: model genuinely missing (the bug this fixes)', () => {
  assert.equal(modelInstalled(tags('gemma3:1b', 'nomic-embed-text:latest'), 'gemma3:4b'), false);
});

test('modelInstalled: untagged wanted matches :latest', () => {
  assert.equal(modelInstalled(tags('nomic-embed-text:latest'), 'nomic-embed-text'), true);
});

test('modelInstalled: tagged wanted does NOT fall back to :latest', () => {
  assert.equal(modelInstalled(tags('gemma3:1b'), 'gemma3:latest'), false);
});

test('modelInstalled: reads the `model` field when `name` is absent', () => {
  assert.equal(modelInstalled({ models: [{ model: 'gemma3:4b' }] }, 'gemma3:4b'), true);
});

test('modelInstalled: empty/garbage inputs are false, never throw', () => {
  assert.equal(modelInstalled(null, 'gemma3:4b'), false);
  assert.equal(modelInstalled({}, 'gemma3:4b'), false);
  assert.equal(modelInstalled(tags('gemma3:4b'), ''), false);
  assert.equal(modelInstalled({ models: 'nope' }, 'gemma3:4b'), false);
});

test('pullPercent: normal progress rounds to a whole percent', () => {
  assert.equal(pullPercent({ total: 100, completed: 50 }), 50);
  assert.equal(pullPercent({ total: 3, completed: 1 }), 33);
});

test('pullPercent: clamps above 100', () => {
  assert.equal(pullPercent({ total: 100, completed: 120 }), 100);
});

test('pullPercent: not-yet-measurable chunks are null', () => {
  assert.equal(pullPercent({ total: 0, completed: 0 }), null);
  assert.equal(pullPercent({ status: 'pulling manifest' }), null);
  assert.equal(pullPercent(null), null);
});

test('MODELS: light default opens with no download wall; smart is the upgrade', () => {
  assert.equal(DEFAULT_MODEL_KEY, 'light');
  assert.equal(MODELS.light.id, 'gemma3:1b');
  assert.equal(MODELS.smart.id, 'gemma4:e4b');
  assert.ok(MODELS.light.approxGB < MODELS.smart.approxGB);
});

test('modelById: maps ids back to catalog entries, null for unknown', () => {
  assert.equal(modelById('gemma3:1b').key, 'light');
  assert.equal(modelById('gemma4:e4b').key, 'smart');
  assert.equal(modelById('nope:1b'), null);
});

test('bundledPythonRelPath: per-OS relocatable CPython path', () => {
  assert.equal(bundledPythonRelPath('darwin'), 'python/bin/python3');
  assert.equal(bundledPythonRelPath('linux'), 'python/bin/python3');
  assert.equal(bundledPythonRelPath('win32'), 'python/python.exe');
});
