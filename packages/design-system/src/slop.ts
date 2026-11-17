/**
 * Slop linter: flags the default choices that make generated UI read as filler.
 * Phase 1 ships the engine and the first patterns; Phase 9 completes the
 * 56-pattern Tastemaker catalog on the same engine.
 */
export interface SlopPattern { id: string; description: string; test: RegExp; files: RegExp }
export interface SlopFinding { pattern: string; file: string; line: number; excerpt: string; description: string }

export const patterns: SlopPattern[] = [
  { id: "gradient-hero", description: "default purple/indigo gradient hero background",
    test: /bg-gradient-to-\w+\s+from-(?:purple|indigo|violet|fuchsia)-\d+/, files: /\.(tsx|jsx|html|css)$/ },
  { id: "placeholder-copy", description: "placeholder copy left in the UI",
    test: /lorem ipsum|placeholder text|your (?:tagline|headline) here/i, files: /\.(tsx|jsx|html|md|mdx)$/ },
  { id: "generic-hero-copy", description: "generic hero line with no product specifics",
    test: /\b(?:welcome to (?:our|the) (?:website|platform)|unlock the power of|revolutionize your)\b/i, files: /\.(tsx|jsx|html|md|mdx)$/ },
  { id: "emoji-heading", description: "decorative emoji in a heading",
    test: /<h[1-3][^>]*>\s*[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u, files: /\.(tsx|jsx|html)$/ },
  { id: "title-case-heading", description: "Title Case Heading instead of sentence case",
    test: /<h[1-3][^>]*>\s*(?:[A-Z][a-z]+\s+){2,}[A-Z][a-z]+\s*</, files: /\.(tsx|jsx|html)$/ },
  { id: "hex-color", description: "raw hex/rgb color instead of an OKLCH token",
    test: /(?:#[0-9a-fA-F]{3,8}\b|rgba?\()/, files: /\.(css|tsx|jsx)$/ },
  { id: "arbitrary-radius", description: "arbitrary radius value instead of a token",
    test: /rounded-\[\d+px\]|border-radius:\s*\d+px/, files: /\.(css|tsx|jsx)$/ },
];

export function scan(file: string, content: string, catalog: SlopPattern[] = patterns): SlopFinding[] {
  const findings: SlopFinding[] = [];
  const lines = content.split("\n");
  for (const p of catalog) {
    if (!p.files.test(file)) continue;
    lines.forEach((text, i) => {
      if (p.test.test(text)) {
        findings.push({ pattern: p.id, file, line: i + 1, excerpt: text.trim().slice(0, 120), description: p.description });
      }
    });
  }
  return findings;
}
