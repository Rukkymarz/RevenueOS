"use client";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ArrowUpRight, X, ShieldCheck } from "lucide-react";
import { AiCoreOrb, CoreAction } from "./ai-core-orb";

export function AiCoreDock({
  command, setCommand, onSubmit, answer, sending, useAI, setUseAI,
}: {
  command: string;
  setCommand: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  answer: string;
  sending: boolean;
  useAI: boolean;
  setUseAI: (value: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && open) { setOpen(false); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); setOpen(true);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    input.current?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, [open]);

  return <aside className={`core-dock ${open ? "core-dock--open" : ""}`} aria-label="AI Core available in every workspace">
    {<button hidden={open} ref={trigger} type="button" className="core-dock__trigger" onClick={() => setOpen(true)} aria-label="Open RevenueOS AI Core; shortcut Control K">
      <AiCoreOrb small /><span>AI Core <kbd>⌘ K</kbd></span>
    </button>}
    {open && <section className="core-dock__panel" role="dialog" aria-modal="false" aria-label="RevenueOS AI Core">
      <header className="core-dock__header"><div className="core-dock__identity"><AiCoreOrb small/><div><strong>RevenueOS AI Core</strong><small>One assistant · Human controlled</small></div></div><button type="button" aria-label="Close AI Core" onClick={() => setOpen(false)}><X size={18}/></button></header>
      <p className="core-dock__guide">Research a prospect, draft a proposal or plan your next revenue move.</p>
      <div className="core-dock__suggestions"><button type="button" onClick={() => setCommand("Draft a business growth proposal with clear assumptions and pricing placeholders.")}>Proposal <ArrowUpRight size={12}/></button><button type="button" onClick={() => setCommand("Prioritize my next five revenue follow-ups.")}>Next actions <ArrowUpRight size={12}/></button></div>
      {answer && <div className="core-dock__answer" role="status" aria-live="polite">{answer}</div>}
      <form onSubmit={onSubmit}><label className="ce-sr-only" htmlFor="core-dock-input">Ask RevenueOS</label><textarea ref={input} id="core-dock-input" value={command} onChange={event => setCommand(event.target.value)} minLength={2} required rows={3} placeholder="Ask RevenueOS to…"/><div className="core-dock__footer"><label><input type="checkbox" checked={useAI} onChange={event => setUseAI(event.target.checked)}/> Use connected AI provider</label><CoreAction pending={sending} disabled={sending || command.trim().length < 2} label="Ask AI Core"/></div></form>
      <p className="core-dock__safety"><ShieldCheck size={13}/> Nothing is published or sent without approval.</p>
    </section>}
  </aside>;
}
