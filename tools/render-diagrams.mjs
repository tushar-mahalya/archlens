import { readdir, readFile, mkdir, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { run } from '@mermaid-js/mermaid-cli';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'dist', 'diagram-check');
await mkdir(output, { recursive: true });

async function markdownFiles(directory) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) found.push(...await markdownFiles(full));
    else if (entry.isFile() && entry.name.endsWith('.md')) found.push(full);
  }
  return found;
}

const files = [
  path.join(root, 'README.md'),
  ...await markdownFiles(path.join(root, 'docs')),
  ...await markdownFiles(path.join(root, 'examples')),
];
let count = 0;
for (const file of files.sort()) {
  const text = await readFile(file, 'utf8');
  for (const match of text.matchAll(/^```mermaid\r?\n([\s\S]*?)^```\s*$/gm)) {
    count += 1;
    const input = path.join(output, `diagram-${count}.mmd`);
    const svg = path.join(output, `diagram-${count}.svg`);
    await writeFile(input, match[1]);
    // The disabled sandbox is limited to the public, fixed fixtures in CI.
    const puppeteerConfig = process.env.CI ? { args: ['--no-sandbox'] } : {};
    await run(input, svg, { puppeteerConfig, quiet: true });
    const rendered = await readFile(svg, 'utf8');
    if (!rendered.includes('<svg')) throw new Error(`No SVG output: ${file}`);
    await rm(input);
    console.log(`Rendered ${path.relative(root, file)} -> ${path.relative(root, svg)}`);
  }
}
if (count === 0) throw new Error('No diagrams found; the validation would be empty.');
console.log(`PASS: ${count} diagrams rendered locally. SVGs are in dist/diagram-check.`);
