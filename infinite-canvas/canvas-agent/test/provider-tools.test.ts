import assert from "node:assert/strict";
import test from "node:test";

import { anthropicTools, openAiTools } from "../src/provider-tools.js";
import { toolNames } from "../src/schemas.js";

test("creates deterministic OpenAI function tools from canvas schemas", () => {
    const tools = openAiTools();
    const expectedNames = [...toolNames].sort();

    assert.deepEqual(tools.map((tool) => tool.name), expectedNames);
    assert.equal(tools[0]?.type, "function");
    assert.equal(tools[0]?.strict, true);
    assert.equal(tools[0]?.parameters.type, "object");
    assert.equal(tools[0]?.parameters.additionalProperties, false);
});

test("creates deterministic Anthropic tools from the same schemas", () => {
    const tools = anthropicTools();

    assert.deepEqual(tools.map((tool) => tool.name), [...toolNames].sort());
    assert.equal(tools[0]?.input_schema.type, "object");
    assert.equal(tools[0]?.input_schema.additionalProperties, false);
});
