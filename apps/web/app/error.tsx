"use client";

export default function WorkspaceError({reset}:{error:Error & {digest?:string};reset:()=>void}) {
  return <main className="auth-screen" role="alert"><h1>We couldn’t open this workspace</h1><p>Try loading it again. If the problem continues, contact your workspace administrator.</p><button className="primary" onClick={reset}>Try again</button></main>;
}
