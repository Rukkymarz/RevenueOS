"use client";
import { createClient } from "@supabase/supabase-js";
import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import Image from "next/image";

export type RevenueAuth={isLoading:boolean;isAuthenticated:boolean;error?:Error;user?:{access_token:string;profile:{sub:string}};signinRedirect:()=>Promise<void>;signoutRedirect:()=>Promise<void>};
export const RevenueAuthContext=createContext<RevenueAuth|null>(null);
export function useRevenueAuth(){const value=useContext(RevenueAuthContext);if(!value)throw new Error("Authentication provider missing");return value;}
let browserClient:SupabaseClient|undefined;
export function getBrowserClient(){
 const build=()=>createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,{auth:{flowType:"pkce",persistSession:typeof window!=="undefined",autoRefreshToken:typeof window!=="undefined",detectSessionInUrl:true,storage:typeof window!=="undefined"?window.sessionStorage:undefined}});
 // Browser-only singleton avoids duplicate auth clients in React Strict Mode.
 // Server rendering always gets a fresh client with persistence disabled.
 if(typeof window==="undefined")return build();
 return browserClient??=build();
}

export function SupabaseAuth({children}:{children:ReactNode}){
 const [client]=useState<SupabaseClient>(getBrowserClient);
 const [session,setSession]=useState<Session|null>(null);const [loading,setLoading]=useState(true);
 const [email,setEmail]=useState("");const [password,setPassword]=useState("");const [code,setCode]=useState("");
 const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [notice,setNotice]=useState("");
 const [mfaReady,setMfaReady]=useState(false);const [factor,setFactor]=useState("");const [qr,setQr]=useState("");const [secret,setSecret]=useState("");
 const [register,setRegister]=useState(false);
 useEffect(()=>{
  let active=true;
  void client.auth.getSession().then(({data,error})=>{if(active){if(error)setError("Could not restore sign-in. Please sign in again.");setSession(data.session);setLoading(false);}});
  const {data}=client.auth.onAuthStateChange((_event,next)=>{if(active){setSession(next);setLoading(false);}});
  return()=>{active=false;data.subscription.unsubscribe();};
 },[client]);
 useEffect(()=>{
  let active=true;
  async function inspect(){
   if(!session){if(active){setMfaReady(false);setFactor("");setQr("");setSecret("");}return;}
   const assurance=await client.auth.mfa.getAuthenticatorAssuranceLevel();
   if(!active)return;
   if(assurance.error){setError("Could not verify your sign-in security. Sign out and try again.");return;}
   setMfaReady(assurance.data.currentLevel==="aal2");
   if(assurance.data.currentLevel!=="aal2"){
    const factors=await client.auth.mfa.listFactors();
    if(active){if(factors.error)setError("Could not load authenticator settings.");else setFactor(factors.data.totp.find(f=>f.status==="verified")?.id||"");}
   }
  }
  void inspect();return()=>{active=false;};
 },[client,session]);
 async function signout(){
  const revoke=mfaReady?await client.rpc("revenueos_revoke_sessions"):null;
  // Still clear provider sessions if a previous attempt already revoked the DB session.
  const result=await client.auth.signOut({scope:"global"});
  if(result.error){setError("Sign out failed. Retry before leaving this device.");throw result.error;}
  setSession(null);setMfaReady(false);setPassword("");setCode("");setQr("");setSecret("");
  if(revoke?.error)setNotice("Signed out. Immediate workspace-session revocation could not be confirmed; contact the administrator if this device was compromised.");
 }
 async function submit(event:React.FormEvent){
  event.preventDefault();setBusy(true);setError("");setNotice("");
  try{
   if(register){const result=await client.auth.signUp({email,password,options:{emailRedirectTo:window.location.origin+"/"}});if(result.error)throw result.error;setNotice("Check your email to verify the account, then sign in. If an account already exists, use Sign in.");setPassword("");}
   else {const result=await client.auth.signInWithPassword({email,password});if(result.error)throw result.error;setPassword("");}
  }catch{setError(register?"Registration could not be completed. Check the details or try signing in.":"Sign-in failed. Check your email, password and email verification.");}finally{setBusy(false);}
 }
 async function enroll(){
  setBusy(true);setError("");
  try{const result=await client.auth.mfa.enroll({factorType:"totp",friendlyName:`RevenueOS ${new Date().toISOString()}`});if(result.error)throw result.error;setFactor(result.data.id);setQr(result.data.totp.qr_code);setSecret(result.data.totp.secret);}catch{setError("Authenticator setup failed. Retry or contact the administrator.");}finally{setBusy(false);}
 }
 async function verify(event:React.FormEvent){
  event.preventDefault();setBusy(true);setError("");
  try{const result=await client.auth.mfa.challengeAndVerify({factorId:factor,code});if(result.error)throw result.error;const refreshed=await client.auth.getSession();setSession(refreshed.data.session);setMfaReady(true);setCode("");setQr("");setSecret("");}catch{setError("Verification failed. Enter the current six-digit authenticator code.");}finally{setBusy(false);}
 }
 if(loading)return <main className="auth-screen"><h1>Connecting securely…</h1></main>;
 if(!session)return <main className="auth-screen"><p className="overline">REVENUEOS</p><h1>{register?"Create your account":"Sign in to RevenueOS"}</h1><p>One secure workspace for your business.</p>
  <form className="settings-form" onSubmit={submit}><label>Email<input type="email" autoComplete="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label><label>Password<input type="password" autoComplete={register?"new-password":"current-password"} required minLength={register?12:1} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label><button className="primary" disabled={busy}>{busy?"Please wait…":register?"Register and verify email":"Sign in"}</button></form>
  <button className="outline" disabled={busy} onClick={()=>{setRegister(!register);setError("");setNotice("");}}>{register?"Back to sign in":"Create an account"}</button>
  <button className="outline" disabled={busy||!email} onClick={()=>{setBusy(true);setError("");void client.auth.resetPasswordForEmail(email,{redirectTo:window.location.origin+"/account/recover"}).then(({error})=>{if(error)setError("Could not request a password reset. Try again.");else setNotice("If the account exists, password reset instructions will arrive by email.");}).finally(()=>setBusy(false));}}>Reset password</button>
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}</main>;
 if(!mfaReady)return <main className="auth-screen"><p className="overline">REVENUEOS · SECURE ACCESS</p><h1>Verify your authenticator</h1><p>Business data requires a second verification step.</p>
  {!factor?<button className="primary" disabled={busy} onClick={()=>void enroll()}>Set up authenticator app</button>:<>
   {qr&&<><p>Scan this code using your authenticator app. Keep the setup key private.</p><Image unoptimized src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(qr)}`} alt="Authenticator setup QR code" width={220} height={220}/><details><summary>Manual setup key</summary><code>{secret}</code></details></>}
   <form className="settings-form" onSubmit={verify}><label>Authenticator code<input autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,""))}/></label><button className="primary" disabled={busy}>Verify and continue</button></form></>}
  {error&&<p role="alert">{error}</p>}<button className="outline" disabled={busy} onClick={()=>void signout().catch(()=>undefined)}>Sign out</button></main>;
 return <RevenueAuthContext.Provider value={{isLoading:false,isAuthenticated:true,user:{access_token:session.access_token,profile:{sub:session.user.id}},signinRedirect:async()=>undefined,signoutRedirect:signout}}>{children}</RevenueAuthContext.Provider>;
}
