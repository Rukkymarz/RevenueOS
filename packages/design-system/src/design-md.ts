/**
 * Non-destructive DESIGN.md merge. A site's committed design tokens live in a
 * fenced ```json block inside DESIGN.md. A later page may add new tokens but may
 * never change or remove a committed one, so page two cannot invent a new radius
 * or recolor the brand. Conflicts are returned, never silently applied.
 */
export type TokenTree = { [k: string]: string | number | TokenTree };
export interface MergeResult { merged: TokenTree; added: string[]; conflicts: { path: string; committed: unknown; proposed: unknown }[] }

const BLOCK = /```json design-tokens\n([\s\S]*?)\n```/;

export function readTokens(designMd: string): TokenTree {
  const m = BLOCK.exec(designMd);
  return m ? (JSON.parse(m[1]!) as TokenTree) : {};
}

export function mergeTokens(committed: TokenTree, proposed: TokenTree, prefix = ""): MergeResult {
  const merged: TokenTree = { ...committed };
  const added: string[] = [];
  const conflicts: MergeResult["conflicts"] = [];
  for (const [k, v] of Object.entries(proposed)) {
    const path = prefix ? `${prefix}.${k}` : k;
    const cur = committed[k];
    if (cur === undefined) {
      merged[k] = v;
      added.push(path);
    } else if (typeof cur === "object" && typeof v === "object") {
      const sub = mergeTokens(cur, v, path);
      merged[k] = sub.merged;
      added.push(...sub.added);
      conflicts.push(...sub.conflicts);
    } else if (cur !== v) {
      conflicts.push({ path, committed: cur, proposed: v });
    }
  }
  return { merged, added, conflicts };
}

export function mergeDesignMd(designMd: string, proposed: TokenTree): { document: string; result: MergeResult } {
  const result = mergeTokens(readTokens(designMd), proposed);
  const block = "```json design-tokens\n" + JSON.stringify(result.merged, null, 2) + "\n```";
  const document = BLOCK.test(designMd) ? designMd.replace(BLOCK, block) : `${designMd.trimEnd()}\n\n${block}\n`;
  return { document, result };
}
