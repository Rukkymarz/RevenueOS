/** Concentric corners: an inner element's radius follows its container (spec 9.6). */
export function concentricRadius(outer: number, padding: number): number {
  if (outer < 0 || padding < 0) throw new Error("radius and padding must be non-negative");
  return Math.max(0, outer - padding);
}

/** True when the inner radius obeys the rule within a 0.5px tolerance. */
export function isConcentric(outer: number, padding: number, inner: number): boolean {
  return Math.abs(inner - concentricRadius(outer, padding)) <= 0.5;
}

/** The five mandatory UI states every surface must render. */
export const UI_STATES = ["empty", "loading", "error", "partial", "ideal"] as const;
export type UiState = (typeof UI_STATES)[number];

export function missingStates(implemented: readonly string[]): UiState[] {
  return UI_STATES.filter((s) => !implemented.includes(s));
}

const KEEP_UPPER = /^(?:[A-Z0-9]{2,}|[A-Z][a-z]+[A-Z]\w*)$/; // acronyms (API, MCP) and camel brands (GitHub)

/** Sentence case: first word capitalised, the rest lower case, acronyms and brand casing kept. */
export function sentenceCase(text: string): string {
  const words = text.trim().split(/\s+/);
  return words
    .map((w, i) => {
      if (KEEP_UPPER.test(w)) return w;
      const lower = w.toLowerCase();
      return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    })
    .join(" ");
}

export function isSentenceCase(text: string): boolean {
  return sentenceCase(text) === text.trim().replace(/\s+/g, " ");
}
