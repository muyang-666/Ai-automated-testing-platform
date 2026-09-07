import test from "node:test";
import assert from "node:assert/strict";
import {
  getStoredProjectId, resolveProjectId, storeProjectId,
} from "../src/utils/projectSelection.js";

const values = new Map();
globalThis.localStorage = {
  getItem: (key) => values.get(key) ?? null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};

test("功能用例页恢复已保存且仍可访问的项目 ID", () => {
  values.clear();
  storeProjectId(7);
  assert.equal(getStoredProjectId(), 7);
  assert.equal(resolveProjectId([{ id: 3 }, { id: 7 }], getStoredProjectId()), 7);
});

test("已保存项目失效时回退首个可访问项目", () => {
  values.clear();
  storeProjectId(99);
  assert.equal(resolveProjectId([{ id: 3 }, { id: 7 }], getStoredProjectId()), 3);
});
