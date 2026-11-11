"use client";

import { motion, useReducedMotion } from "framer-motion";

/** Decorative orb; never presents invented AI progress. Inputs reflect real workflow state. */
export type CoreState = "idle" | "thinking" | "researching" | "generating" | "executing" | "approval";
const STATUS: Record<CoreState,string> = {
  idle:"Ready",thinking:"Processing request",researching:"Research in progress",
  generating:"Generating content",executing:"Executing workflow",approval:"Waiting for approval",
};
export function AiCoreOrb({state="idle",small=false}:{state?:CoreState;small?:boolean}) {
  const reducedMotion = useReducedMotion();
  return <motion.div className={`ai-core-orb ${small?"ai-core-orb--small":""} ai-core-orb--${state}`}
    role="img" aria-label={`RevenueOS AI Core: ${STATUS[state]}`}
    animate={reducedMotion ? undefined : {scale: state==="thinking" ? [1,1.055,1] : [1,1.018,1]}}
    transition={{duration:state==="thinking"?1.25:4,repeat:Infinity,ease:"easeInOut"}}>
    <span className="ai-core-orb__halo" aria-hidden="true" />
    <span className="ai-core-orb__rotator" aria-hidden="true" />
    <span className="ai-core-orb__glass" aria-hidden="true"><span className="ai-core-orb__letter">R</span></span>
    <span className="ai-core-orb__satellite ai-core-orb__satellite--one" aria-hidden="true" />
    <span className="ai-core-orb__satellite ai-core-orb__satellite--two" aria-hidden="true" />
  </motion.div>;
}
export function CoreAction({label="Run command",disabled=false,pending=false}:{label?:string;disabled?:boolean;pending?:boolean}) {
  return <button className="core-action-button" type="submit" disabled={disabled} aria-busy={pending}>
    <span className="core-action-button__border" aria-hidden="true" />
    <svg className="core-action-button__sparkle" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5Z"/><path d="M19 2v5M16.5 4.5h5"/></svg>
    <span>{pending?"Working…":label}</span>
  </button>;
}
