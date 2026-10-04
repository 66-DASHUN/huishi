import { expect, test } from "bun:test";

import { startupLogLines } from "../src/http-server.js";
import type { CanvasAgentConfig } from "../src/config.js";


test("startup logs never expose the connection token", () => {
    const config = {
        url: "http://127.0.0.1:17371",
        token: "top-secret-connect-token",
    } as CanvasAgentConfig;

    const lines = startupLogLines(config);

    expect(lines).toContain("Connect token: configured");
    expect(lines.join("\n")).not.toContain(config.token);
});
