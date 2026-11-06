import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, lstatSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const CLI = join(ROOT, "node_modules", "skills", "bin", "cli.mjs");
const SKILL = join(ROOT, "skills", "archlens");
const AGENTS = [
  "claude-code", "codex", "cursor", "github-copilot", "gemini-cli",
  "opencode", "cline", "roo", "windsurf", "devin",
];
const AGENT_LABELS = [
  "Claude Code", "Codex", "Cursor", "GitHub Copilot", "Gemini CLI",
  "OpenCode", "Cline", "Roo Code", "Windsurf", "Devin for Terminal",
];
const PYTHON = process.env.ARCHLENS_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3");

function sandbox(run) {
  const root = mkdtempSync(join(tmpdir(), "archlens-skills-"));
  const home = join(root, "home");
  const project = join(root, "project");
  mkdirSync(home);
  mkdirSync(project);
  const env = {
    ...process.env,
    HOME: home,
    USERPROFILE: home,
    XDG_CONFIG_HOME: join(home, ".config"),
    DO_NOT_TRACK: "1",
    DISABLE_TELEMETRY: "1",
    NO_COLOR: "1",
    FORCE_COLOR: "0",
    NODE_DISABLE_COMPILE_CACHE: "1",
  };
  delete env.ARCHLENS_CONFIG;
  delete env.CLAUDE_CONFIG_DIR;
  delete env.INSTALL_INTERNAL_SKILLS;
  try {
    run({ root, home, project, env });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function runCommand(executable, args, context, stdoutOnly = false) {
  const result = spawnSync(executable, args, {
    cwd: context.project, env: context.env, encoding: "utf8", timeout: 120000,
    maxBuffer: 2 * 1024 * 1024, windowsHide: true,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, `${executable} exited ${result.status}\n${result.stdout}\n${result.stderr}`);
  return stdoutOnly ? result.stdout : result.stdout + result.stderr;
}

function runSkills(args, context) {
  return runCommand(process.execPath, [CLI, ...args], context, args.includes("--json"));
}

function filesUnder(root, current = root) {
  return readdirSync(current, { withFileTypes: true })
    .filter((entry) => entry.name !== "__pycache__")
    .flatMap((entry) => {
      const path = join(current, entry.name);
      return entry.isDirectory() ? filesUnder(root, path) : [relative(root, path)];
    })
    .sort();
}

function hash(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function verifyBundle(target, copied) {
  if (copied) assert.equal(lstatSync(target).isSymbolicLink(), false, `${target} should be a copy`);
  const expected = filesUnder(SKILL);
  assert.deepEqual(filesUnder(target), expected, `Bundle differs at ${target}`);
  for (const file of expected) assert.equal(hash(join(target, file)), hash(join(SKILL, file)), file);
}

function verifyChecker(target, context) {
  const output = runCommand(PYTHON, [
    join(target, "scripts", "archlens.py"), "check", "--root",
    join(ROOT, "examples", "order-service"), "--strict", "--json",
  ], context);
  assert.equal(JSON.parse(output).ok, true);
}

test("discovery exposes only the portable skill by default", { timeout: 120000 }, () => {
  sandbox((context) => {
    for (const extra of [[], ["--full-depth"]]) {
      const output = runSkills(["add", ROOT, "--list", ...extra], context);
      assert.match(output, /Found 1 skill\b/);
      assert.match(output, /\barchlens\b/);
    }
    context.env.INSTALL_INTERNAL_SKILLS = "1";
    const internal = runSkills(["add", ROOT, "--list"], context);
    assert.match(internal, /Found 6 skills\b/);
  });
});

for (const global of [false, true]) {
  test(`copy installs complete bundles for ten adapters (${global ? "global" : "project"})`, { timeout: 120000 }, () => {
    sandbox((context) => {
      const args = ["add", ROOT, "--skill", "archlens", "--agent", ...AGENTS, "--copy", "--yes", "--json"];
      if (global) args.push("--global");
      const output = runSkills(args, context);
      const result = JSON.parse(output);
      assert.equal(result.length, 1);
      assert.equal(result[0].status, "installed");
      assert.equal(result[0].mode, "copy");
      assert.deepEqual(result[0].agents.sort(), [...AGENT_LABELS].sort());
      const base = global ? context.home : context.project;
      const paths = [
        join(base, ".agents", "skills", "archlens"),
        join(base, ".claude", "skills", "archlens"),
        join(base, ".roo", "skills", "archlens"),
        global
          ? join(base, ".codeium", "windsurf", "skills", "archlens")
          : join(base, ".windsurf", "skills", "archlens"),
        global
          ? join(base, ".config", "devin", "skills", "archlens")
          : join(base, ".devin", "skills", "archlens"),
      ];
      for (const path of paths) verifyBundle(path, true);
      verifyChecker(paths[0], context);
      const unrelated = join(base, ".agents", "skills", "other-skill");
      mkdirSync(unrelated);
      writeFileSync(join(unrelated, "SKILL.md"), "unrelated");
      const removal = ["remove", "archlens", "--yes"];
      if (global) removal.push("--global");
      runSkills(removal, context);
      for (const path of paths) assert.equal(existsSync(path), false, `Not removed: ${path}`);
      assert.equal(existsSync(join(unrelated, "SKILL.md")), true, "Unrelated skill was removed");
    });
  });

  test(`default install keeps resources accessible (${global ? "global" : "project"})`, { timeout: 120000 }, () => {
    sandbox((context) => {
      const args = ["add", ROOT, "--skill", "archlens", "--agent", "claude-code", "codex", "--yes"];
      if (global) args.push("--global");
      runSkills(args, context);
      const base = global ? context.home : context.project;
      for (const directory of [".agents", ".claude"]) {
        verifyBundle(join(base, directory, "skills", "archlens"), false);
      }
    });
  });
}
