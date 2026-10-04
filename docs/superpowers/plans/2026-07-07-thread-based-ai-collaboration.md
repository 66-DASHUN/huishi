# Thread-Based AI Collaboration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure this repository so the current Codex thread acts as the single user-facing control surface while Claude is used behind the scenes for planning, review, and PR-description drafting.

**Architecture:** Store the collaboration contract in project guidance files. Codex reads `AGENTS.md` and orchestrates normal user requests from the thread; Claude reads `CLAUDE.md` and stays in an advisory role unless explicitly asked otherwise. `AI_WORKFLOW.md` is the shared source of truth for both agents.

**Tech Stack:** Codex desktop thread, Codex project guidance, Claude Code CLI, Git diff review, Markdown project instructions.

---

### Task 1: Add Shared Collaboration Contract

**Files:**
- Create: `AI_WORKFLOW.md`

- [ ] **Step 1: Create shared workflow**

Create `AI_WORKFLOW.md` with the role split, trigger rules, and default end-to-end workflow.

- [ ] **Step 2: Verify readability**

Run: `Get-Content .\AI_WORKFLOW.md`
Expected: The file explains that the user can send normal requirements in the Codex thread and does not need to use a special prefix.

### Task 2: Add Codex Project Guidance

**Files:**
- Create: `AGENTS.md`

- [ ] **Step 1: Create Codex guidance**

Create `AGENTS.md` that tells Codex to read `AI_WORKFLOW.md`, use Claude for plans and reviews when helpful, and keep implementation work in Codex.

- [ ] **Step 2: Verify Codex guidance**

Run: `Get-Content .\AGENTS.md`
Expected: The file names the thread-based workflow and the Claude/Codex role split.

### Task 3: Refresh Claude Project Guidance

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace unclear guidance with stable ASCII instructions**

Rewrite `CLAUDE.md` so Claude understands it is being called by Codex for planning, review, and PR description work.

- [ ] **Step 2: Preserve known attached project context**

Keep the known attached project path `D:\AI\infinite-canvas\infinite-canvas` in the file.

- [ ] **Step 3: Verify Claude guidance**

Run: `Get-Content .\CLAUDE.md`
Expected: The file is readable and asks Claude to output user-facing content in Simplified Chinese.

### Task 4: Verify Local Tool Availability

**Files:**
- None

- [ ] **Step 1: Check Codex CLI**

Run: `codex --version`
Expected: The command exits successfully.

- [ ] **Step 2: Check Claude CLI**

Run: `claude --version`
Expected: The command exits successfully, or the final response reports that Claude CLI verification failed.

- [ ] **Step 3: Check git status**

Run: `git status --short`
Expected: Existing user changes remain present; only the new guidance files are added or modified by this deployment.
