"use client";
import { getBrowserClient, useRevenueAuth } from "../../../components/supabase-auth";
import { useState } from "react";
import Link from "next/link";

export default function Recovery(){
 const auth=useRevenueAuth();
 const [password,setPassword]=useState("");const [confirmation,setConfirmation]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);const [done,setDone]=useState(false);
 return <main className="auth-screen"><p className="overline">REVENUEOS</p><h1>Reset your password</h1>
  <p>Complete verified sign-in and your authenticator check before changing your password.</p>
  {done?<><p role="status">Password updated and sessions signed out.</p><Link className="primary" href="/">Return to sign in</Link></>:<form className="settings-form" onSubmit={async event=>{
   event.preventDefault();setError("");if(password!==confirmation){setError("The passwords must match.");return;}setBusy(true);
   try{
    const client=getBrowserClient();
    const result=await client.auth.updateUser({password});if(result.error)throw result.error;
    await auth.signoutRedirect();
    setPassword("");setConfirmation("");setDone(true);
   }catch{setError("Password reset could not be completed. Request a fresh recovery email or contact the administrator.");}finally{setBusy(false);}
  }}><label>New password<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label><label>Confirm password<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label><button className="primary" disabled={busy}>Update password and sign out</button></form>}
  {error&&<p role="alert">{error}</p>}
 </main>;
}
