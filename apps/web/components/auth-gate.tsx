"use client";
import { AuthProvider, useAuth } from "react-oidc-context";
import { RevenueAuthContext, SupabaseAuth } from "./supabase-auth";
import type { UserManagerSettings } from "oidc-client-ts";
import { useEffect } from "react";
const authority = process.env.NEXT_PUBLIC_OIDC_ISSUER ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8080/realms/revenueos" : "");
const callbackUrl = typeof window === "undefined" ? "http://localhost:3000/" : window.location.origin + "/";
const settings: UserManagerSettings = {
  authority,
  client_id: "revenueos-web",
  redirect_uri: callbackUrl,
  post_logout_redirect_uri: callbackUrl,
  response_type: "code",
  scope: "openid profile email",
  automaticSilentRenew: false,
  // Session storage, not permanent localStorage; deploy behind TLS and strict CSP.
};
function Worker() {
  useEffect(() => { if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  } }, []);
  return null;
}
export function AuthGate({children}:{children:React.ReactNode}) {
  if(process.env.NEXT_PUBLIC_AUTH_PROVIDER==="supabase"){
    if(!process.env.NEXT_PUBLIC_SUPABASE_URL?.startsWith("https://")||!process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY)return <main className="auth-screen" role="alert"><h1>Secure sign-in is awaiting configuration</h1></main>;
    return <SupabaseAuth><Worker/>{children}</SupabaseAuth>;
  }
  // Fail closed: never redirect deployed users to a developer's localhost IdP.
  if (!authority || (typeof window !== "undefined" && window.location.protocol === "https:" && !authority.startsWith("https://"))) {
    return <main className="auth-screen" role="alert"><p className="overline">REVENUEOS</p><h1>Getting your workspace ready</h1><p>Secure sign-in is awaiting configuration by the app owner. Your business data stays protected until setup is complete.</p></main>;
  }
  return <AuthProvider {...settings} onSigninCallback={() => {
    window.history.replaceState({},document.title,"/");
  }}><LegacyBridge><Worker />{children}</LegacyBridge></AuthProvider>;
}
function LegacyBridge({children}:{children:React.ReactNode}){
 const auth=useAuth();
 return <RevenueAuthContext.Provider value={{isLoading:auth.isLoading,isAuthenticated:auth.isAuthenticated,error:auth.error,user:auth.user?{access_token:auth.user.access_token,profile:{sub:auth.user.profile.sub}}:undefined,signinRedirect:async()=>{await auth.signinRedirect();},signoutRedirect:async()=>{await auth.signoutRedirect();}}}>{children}</RevenueAuthContext.Provider>;
}
