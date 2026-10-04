#!/usr/bin/env node

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const CONFIGURED_TIMEOUT_MS = Number.parseInt(process.env.CLAUDE_MCP_TIMEOUT_MS || "1800000", 10);
const DEFAULT_TIMEOUT_MS =
  Number.isFinite(CONFIGURED_TIMEOUT_MS) && CONFIGURED_TIMEOUT_MS > 0 ? CONFIGURED_TIMEOUT_MS : 1_800_000;
const MAX_PROMPT_CHARS = 120_000;
const MAX_OUTPUT_CHARS = 60_000;
const DEFAULT_CWD = process.env.CLAUDE_MCP_CWD || process.cwd();
const DEFAULT_MODEL = process.env.CLAUDE_MCP_MODEL || "";

const ResponseFormatSchema = z.enum(["markdown", "json"]).default("markdown");

const CommonSchema = z
  .object({
    requirement: z
      .string()
      .min(1)
      .max(MAX_PROMPT_CHARS)
      .describe("The user's requirement or task description."),
    context: z
      .string()
      .max(MAX_PROMPT_CHARS)
      .optional()
      .describe("Optional repository context, logs, code snippets, or constraints."),
    response_format: ResponseFormatSchema.describe("Return markdown for humans or json for downstream processing.")
  })
  .strict();

const ReviewSchema = z
  .object({
    instructions: z
      .string()
      .min(1)
      .max(MAX_PROMPT_CHARS)
      .describe("What Claude should review and the requested review standard."),
    diff: z
      .string()
      .min(1)
      .max(MAX_PROMPT_CHARS)
      .describe("Git diff, patch, or implementation summary to review."),
    response_format: ResponseFormatSchema.describe("Return markdown for humans or json for downstream processing.")
  })
  .strict();

const PrDescriptionSchema = z
  .object({
    requirement: z.string().min(1).max(MAX_PROMPT_CHARS).describe("Original user request or product requirement."),
    implementation_summary: z.string().min(1).max(MAX_PROMPT_CHARS).describe("What changed."),
    test_results: z.string().max(20_000).optional().describe("Verification commands and results."),
    diff_summary: z.string().max(MAX_PROMPT_CHARS).optional().describe("Optional git diff or concise diff summary."),
    response_format: ResponseFormatSchema.describe("Return markdown for humans or json for downstream processing.")
  })
  .strict();

type ClaudeResult = {
  ok: boolean;
  text: string;
  stderr?: string;
  exitCode?: number | null;
  truncated?: boolean;
};

type ClaudeJob = {
  id: string;
  status: "running" | "succeeded" | "failed";
  createdAt: string;
  finishedAt?: string;
  result?: ClaudeResult;
};

const jobs = new Map<string, ClaudeJob>();

function resolveClaudeCommand(): string {
  const configured = process.env.CLAUDE_CLI_PATH;
  if (configured) {
    return configured;
  }

  const knownWindowsExe = "E:\\Phthon learning space\\tools\\Node\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe";
  if (process.platform === "win32" && existsSync(knownWindowsExe)) {
    return knownWindowsExe;
  }

  const knownWindowsCmd = "E:\\Phthon learning space\\tools\\Node\\claude.cmd";
  if (process.platform === "win32" && existsSync(knownWindowsCmd)) {
    return knownWindowsCmd;
  }

  return process.platform === "win32" ? "claude.cmd" : "claude";
}

function truncate(text: string, maxChars: number): { text: string; truncated: boolean } {
  if (text.length <= maxChars) {
    return { text, truncated: false };
  }
  return {
    text: `${text.slice(0, maxChars)}\n\n[truncated: output exceeded ${maxChars} characters]`,
    truncated: true
  };
}

function buildClaudeSpawn(command: string, args: string[]): { command: string; args: string[] } | { error: string } {
  if (process.platform !== "win32" || !command.toLowerCase().endsWith(".cmd")) {
    return { command, args };
  }

  for (const arg of args) {
    if (!/^[A-Za-z0-9._:-]+$/.test(arg)) {
      return { error: `Error: unsafe Claude CLI argument rejected: ${arg}` };
    }
  }

  const commandLine = `call "${command.replace(/"/g, "")}" ${args.join(" ")}`;
  return {
    command: process.env.ComSpec || "cmd.exe",
    args: ["/d", "/c", commandLine]
  };
}

function formatPrompt(role: "plan" | "review" | "pr", body: string, responseFormat: "markdown" | "json"): string {
  const formatInstruction =
    responseFormat === "json"
      ? "Return strict JSON only. Do not wrap it in Markdown fences."
      : "Return concise Markdown. User-facing text must be Simplified Chinese.";

  const common =
    "You are Claude advising Codex inside a local development workflow. " +
    "Do not edit files, run commands, request permissions, or ask the user to open another Claude page. " +
    "Codex owns implementation and verification. " +
    formatInstruction;

  if (role === "plan") {
    return `${common}

Task: produce a concise implementation plan, acceptance criteria, risks, and suggested verification.

${body}`;
  }

  if (role === "review") {
    return `${common}

Task: review the provided Codex output. Group findings as BLOCKER, SHOULD_FIX, and NIT. Focus on bugs, regressions, missing tests, and maintainability risks.

${body}`;
  }

  return `${common}

Task: create a concise PR description. Use sections: Summary, Testing, Risks.

${body}`;
}

async function runClaude(prompt: string): Promise<ClaudeResult> {
  const promptSize = Buffer.byteLength(prompt, "utf8");
  if (promptSize > MAX_PROMPT_CHARS * 4) {
    return {
      ok: false,
      text: `Error: prompt is too large (${promptSize} bytes). Provide a smaller diff or summary.`
    };
  }

  const command = resolveClaudeCommand();
  const args = ["-p", "--output-format", "text", "--permission-mode", "plan"];
  if (DEFAULT_MODEL) {
    args.push("--model", DEFAULT_MODEL);
  }
  const spawnConfig = buildClaudeSpawn(command, args);
  if ("error" in spawnConfig) {
    return {
      ok: false,
      text: spawnConfig.error
    };
  }

  return new Promise((resolve) => {
    const child = spawn(spawnConfig.command, spawnConfig.args, {
      cwd: DEFAULT_CWD,
      env: process.env,
      windowsHide: true,
      shell: false
    });

    let stdout = "";
    let stderr = "";
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) {
        return;
      }
      settled = true;
      child.kill("SIGTERM");
      resolve({
        ok: false,
        text: `Error: Claude CLI timed out after ${DEFAULT_TIMEOUT_MS} ms. Try sending a smaller prompt.`,
        stderr
      });
    }, DEFAULT_TIMEOUT_MS);

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdin.end(prompt);
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
    });

    child.on("error", (error: Error) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve({
        ok: false,
        text:
          `Error: failed to start Claude CLI (${error.message}). ` +
          "Check that Claude Code is installed and set CLAUDE_CLI_PATH if needed.",
        stderr
      });
    });

    child.on("close", (exitCode: number | null) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);

      const clipped = truncate(stdout.trim() || stderr.trim(), MAX_OUTPUT_CHARS);
      resolve({
        ok: exitCode === 0,
        text: clipped.text || `Claude CLI exited with code ${exitCode} and no output.`,
        stderr: stderr.trim() || undefined,
        exitCode,
        truncated: clipped.truncated
      });
    });
  });
}

function startClaudeJob(prompt: string): ClaudeJob {
  const job: ClaudeJob = {
    id: randomUUID(),
    status: "running",
    createdAt: new Date().toISOString()
  };
  jobs.set(job.id, job);
  void runClaude(prompt)
    .then((result) => {
      job.status = result.ok ? "succeeded" : "failed";
      job.finishedAt = new Date().toISOString();
      job.result = result;
    })
    .catch((error: unknown) => {
      job.status = "failed";
      job.finishedAt = new Date().toISOString();
      job.result = {
        ok: false,
        text: error instanceof Error ? error.message : String(error)
      };
    });
  return job;
}

function toToolResponse(result: ClaudeResult) {
  return {
    isError: !result.ok,
    content: [{ type: "text" as const, text: result.text }],
    structuredContent: result
  };
}

function toJobResponse(job: ClaudeJob) {
  return {
    content: [
      {
        type: "text" as const,
        text: JSON.stringify(
          {
            ok: true,
            job_id: job.id,
            status: job.status,
            created_at: job.createdAt
          },
          null,
          2
        )
      }
    ],
    structuredContent: {
      ok: true,
      job_id: job.id,
      status: job.status,
      created_at: job.createdAt
    }
  };
}

const server = new McpServer({
  name: "claude-mcp-server",
  version: "0.1.0"
});

server.registerTool(
  "claude_plan",
  {
    title: "Claude Plan",
    description:
      "Ask Claude CLI for a read-only implementation plan, acceptance criteria, risks, and verification suggestions for a user requirement.",
    inputSchema: CommonSchema.shape,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true
    }
  },
  async (params) => {
    const prompt = formatPrompt(
      "plan",
      `Requirement:\n${params.requirement}\n\nContext:\n${params.context || "(none provided)"}`,
      params.response_format
    );
    return toToolResponse(await runClaude(prompt));
  }
);

server.registerTool(
  "claude_plan_async",
  {
    title: "Claude Plan Async",
    description:
      "Start a long-running Claude planning job and return immediately with a job id. Poll with claude_job_status.",
    inputSchema: CommonSchema.shape,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true
    }
  },
  async (params) => {
    const prompt = formatPrompt(
      "plan",
      `Requirement:\n${params.requirement}\n\nContext:\n${params.context || "(none provided)"}`,
      params.response_format
    );
    return toJobResponse(startClaudeJob(prompt));
  }
);

server.registerTool(
  "claude_review",
  {
    title: "Claude Review",
    description:
      "Ask Claude CLI to review a Codex-produced diff or implementation summary. Claude only returns advisory findings and does not edit files.",
    inputSchema: ReviewSchema.shape,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true
    }
  },
  async (params) => {
    const prompt = formatPrompt(
      "review",
      `Instructions:\n${params.instructions}\n\nDiff or implementation summary:\n${params.diff}`,
      params.response_format
    );
    return toToolResponse(await runClaude(prompt));
  }
);

server.registerTool(
  "claude_review_async",
  {
    title: "Claude Review Async",
    description:
      "Start a long-running Claude review job and return immediately with a job id. Poll with claude_job_status.",
    inputSchema: ReviewSchema.shape,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true
    }
  },
  async (params) => {
    const prompt = formatPrompt(
      "review",
      `Instructions:\n${params.instructions}\n\nDiff or implementation summary:\n${params.diff}`,
      params.response_format
    );
    return toJobResponse(startClaudeJob(prompt));
  }
);

server.registerTool(
  "claude_pr_description",
  {
    title: "Claude PR Description",
    description:
      "Ask Claude CLI to draft a concise PR description from the requirement, implementation summary, tests, and optional diff summary.",
    inputSchema: PrDescriptionSchema.shape,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true
    }
  },
  async (params) => {
    const prompt = formatPrompt(
      "pr",
      `Requirement:\n${params.requirement}

Implementation summary:\n${params.implementation_summary}

Testing:\n${params.test_results || "(not provided)"}

Diff summary:\n${params.diff_summary || "(not provided)"}`,
      params.response_format
    );
    return toToolResponse(await runClaude(prompt));
  }
);

server.registerTool(
  "claude_pr_description_async",
  {
    title: "Claude PR Description Async",
    description:
      "Start a long-running Claude PR-description job and return immediately with a job id. Poll with claude_job_status.",
    inputSchema: PrDescriptionSchema.shape,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true
    }
  },
  async (params) => {
    const prompt = formatPrompt(
      "pr",
      `Requirement:\n${params.requirement}

Implementation summary:\n${params.implementation_summary}

Testing:\n${params.test_results || "(not provided)"}

Diff summary:\n${params.diff_summary || "(not provided)"}`,
      params.response_format
    );
    return toJobResponse(startClaudeJob(prompt));
  }
);

server.registerTool(
  "claude_job_status",
  {
    title: "Claude Job Status",
    description: "Poll the result of a long-running Claude async job.",
    inputSchema: z
      .object({
        job_id: z.string().min(1).describe("Job id returned by an async Claude tool.")
      })
      .strict().shape,
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  async (params) => {
    const job = jobs.get(params.job_id);
    if (!job) {
      return toToolResponse({
        ok: false,
        text: `Error: Claude job not found: ${params.job_id}`
      });
    }
    const body = {
      ok: job.status === "succeeded",
      job_id: job.id,
      status: job.status,
      created_at: job.createdAt,
      finished_at: job.finishedAt,
      result: job.result
    };
    return {
      isError: job.status === "failed",
      content: [{ type: "text" as const, text: JSON.stringify(body, null, 2) }],
      structuredContent: body
    };
  }
);

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("claude-mcp-server running via stdio");
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  console.error(message);
  process.exit(1);
});
