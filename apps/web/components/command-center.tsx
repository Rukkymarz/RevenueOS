"use client";

import { ArrowRight, ArrowUpRight, CheckCircle2, ChevronRight, ClipboardCheck, FileText,
  Globe2, Megaphone, Plus, ShieldCheck, Target, TrendingUp, UsersRound,
  WandSparkles, Zap } from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { AiCoreOrb, CoreAction } from "./ai-core-orb";

type Data = Record<string, unknown>;
type Workspace = "Dashboard" | "Leads" | "Clients" | "Opportunities" | "Campaigns" | "Content" | "Websites" | "Media Studio" | "Tasks" | "Approvals" | "Reports" | "Settings" | "AI Assistant" | "Proposals";
type Props = {
  report: Data; leads: Data[]; loading: boolean; leadError: string;
  command: string; setCommand: (v: string) => void; answer: string;
  sending: boolean; useAI: boolean; setUseAI: (v: boolean) => void;
  onSubmit: (event: FormEvent) => void; navigate: (page: Workspace, create?: boolean) => void;
};
function number(value: unknown): number { const n = Number(value); return Number.isFinite(n) ? n : 0; }
function usd(value: unknown): string { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(number(value)); }
const suggestions = [
  { label: "Find opportunities", command: "Outline an evidence-based lead discovery plan. Ask me for my target geography and industry before researching." },
  { label: "Create a proposal", command: "Help me draft a client proposal. Ask for the client's needs and services before pricing." },
  { label: "Build a campaign", command: "Create a practical 30-day campaign plan with channels, measurable targets, and approval checkpoints." },
];
const shortcuts: {label: string; workspace: Workspace; icon: ReactNode; create?: boolean}[] = [
  {label:"New lead", workspace:"Leads", create:true, icon:<Target size={17}/>},
  {label:"Proposal", workspace:"Proposals", create:true, icon:<FileText size={17}/>},
  {label:"Website", workspace:"Websites", create:true, icon:<Globe2 size={17}/>},
  {label:"Campaign", workspace:"Campaigns", create:true, icon:<Megaphone size={17}/>},
];
export function CommandCenter({report,leads,loading,leadError,command,setCommand,answer,sending,useAI,setUseAI,onSubmit,navigate}:Props) {
  const tasks = Array.isArray(report.due_tasks) ? report.due_tasks as Data[] : [];
  const approvals = Array.isArray(report.pending_approvals) ? report.pending_approvals as Data[] : [];
  const mission = tasks.find(item => item.status !== "done");
  const priorityLeads = [...leads].sort((a,b) => number(b.score)-number(a.score)).slice(0,3);
  const metrics = [
    {title:"Monthly recurring",value:usd(report.mrr),sub:"Recorded MRR",icon:<TrendingUp size={17}/>,tone:"mint"},
    {title:"Open pipeline",value:usd(report.pipeline_value),sub:"Potential deal value",icon:<Zap size={17}/>,tone:"cyan"},
    {title:"Active clients",value:String(number(report.clients_active)),sub:"In this workspace",icon:<UsersRound size={17}/>,tone:"violet"},
    {title:"Needs attention",value:String(tasks.length+approvals.length),sub:`${tasks.length} tasks · ${approvals.length} approvals`,icon:<ClipboardCheck size={17}/>,tone:"amber"},
  ];
  return <div className="neo-home">
    <div className="neo-eyebrow"><span className="neo-live-dot"/> REVENUE INTELLIGENCE <span> / COMMAND CENTER</span></div>
    <section className="neo-core" aria-label="AI Core command center">
      <div className="neo-core-ambient" aria-hidden="true"/>
      <div className="neo-core-visual"><AiCoreOrb state={sending ? "thinking" : approvals.length ? "approval" : "idle"}/></div>
      <div className="neo-core-status"><span className="neo-live-dot"/>{sending ? "PROCESSING REQUEST" : "AI CORE READY"}</div>
      <h2>What should we accomplish today?</h2>
      <p>One command for research, proposals, websites and growth. You stay in control.</p>
      <div className="neo-suggestions" aria-label="Suggested commands">{suggestions.map(item => <button type="button" key={item.label} onClick={()=>setCommand(item.command)}>{item.label}<ArrowUpRight size={14}/></button>)}</div>
      <form className="neo-command-form" onSubmit={onSubmit}>
        <label className="neo-sr-only" htmlFor="neo-prompt">Give RevenueOS an instruction</label>
        <textarea id="neo-prompt" value={command} onChange={e=>setCommand(e.target.value)} placeholder="Ask RevenueOS to find opportunities, write a proposal, plan a campaign…" minLength={2} required rows={2}/>
        <div className="neo-command-row"><label className="neo-ai-toggle"><input type="checkbox" checked={useAI} onChange={e=>setUseAI(e.target.checked)}/><span>Use connected AI provider</span></label><CoreAction label="Run command" pending={sending} disabled={sending||command.trim().length<2}/></div>
      </form>
      {answer&&<div className="neo-answer" role="status" aria-live="polite"><strong>AI Core response</strong><p>{answer}</p></div>}
      <div className="neo-safety"><ShieldCheck size={14}/> Nothing is sent, published or deployed without an approval step.</div>
    </section>
    <section className="neo-metrics" aria-label="Business snapshot">{metrics.map(item=><article className="neo-stat" key={item.title}><div className="neo-stat-header"><span>{item.title}</span><span className={`neo-stat-icon ${item.tone}`}>{item.icon}</span></div><strong>{loading?"—":item.value}</strong><small>{item.sub}</small></article>)}</section>
    <section className="neo-bottom-grid" aria-label="Priorities and quick actions">
      <div className="neo-panel">
        <div className="neo-panel-heading"><div><span className="neo-kicker">FOCUS</span><h3>Next best actions</h3></div><button onClick={()=>navigate("Tasks")} className="neo-link">All tasks <ChevronRight size={15}/></button></div>
        <button className="neo-priority" onClick={()=>navigate("Tasks",!mission)}><span className="neo-priority-symbol"><CheckCircle2 size={18}/></span><span><strong>{mission ? String(mission.title||"Due task") : "Set your first daily mission"}</strong><small>{mission ? "A task needs your attention" : "Start with one action that moves revenue forward"}</small></span><ArrowRight size={16}/></button>
        <button className="neo-priority" onClick={()=>navigate("Approvals")}><span className="neo-priority-symbol violet"><ShieldCheck size={18}/></span><span><strong>{approvals.length} approvals pending</strong><small>{approvals.length ? "Review content before it goes out" : "No outgoing work waiting for review"}</small></span><ArrowRight size={16}/></button>
      </div>
      <div className="neo-panel"><div className="neo-panel-heading"><div><span className="neo-kicker">PIPELINE</span><h3>Priority leads</h3></div><button onClick={()=>navigate("Leads")} className="neo-link">View all <ChevronRight size={15}/></button></div>
      {leadError && <p className="neo-error" role="alert">Could not retrieve leads: {leadError}</p>}
      {!leadError&&(priorityLeads.length ? priorityLeads.map((lead,i)=><button key={String(lead.id??i)} className="neo-lead" onClick={()=>navigate("Leads")}><span className="neo-lead-avatar">{String(lead.business_name||"L").slice(0,2).toUpperCase()}</span><span><strong>{String(lead.business_name||"Unnamed lead")}</strong><small>{String(lead.industry||lead.location||lead.stage||"New lead")}</small></span><span className="neo-score">{lead.score==null ? "—" : String(lead.score)}<small>score</small></span></button>) : <div className="neo-empty">{loading ? "Loading leads…" : "No leads recorded yet."}<button onClick={()=>navigate("Leads",true)}>Add a lead <Plus size={14}/></button></div>)}
      </div>
    </section>
    <section className="neo-create" aria-label="Create work"><div><span className="neo-kicker">WORKSPACES</span><h3>Make your next move</h3><p>Only the tools you need, when you need them.</p></div><div className="neo-create-actions">{shortcuts.map(item=><button key={item.label} onClick={()=>navigate(item.workspace,item.create)}>{item.icon}<span>{item.label}</span><ChevronRight size={15}/></button>)}</div></section>
    <div className="neo-footer"><WandSparkles size={14}/> Metrics are sourced from your workspace, not invented estimates.</div>
  </div>;
}
