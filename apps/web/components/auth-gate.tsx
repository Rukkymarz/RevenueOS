"use client";
import { AuthProvider } from "react-oidc-context";
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
  // Fail closed: never redirect deployed users to a developer's localhost IdP.
  if (!authority || (typeof window !== "undefined" && window.location.protocol === "https:" && !authority.startsWith("https://"))) {
    return <main className="auth-screen" role="alert"><p className="overline">REVENUEOS</p><h1>Getting your workspace ready</h1><p>Secure sign-in is awaiting configuration by the app owner. Your business data stays protected until setup is complete.</p></main>;
  }
  return <AuthProvider {...settings} onSigninCallback={() => {
    window.history.replaceState({},document.title,"/");
  }}><Worker />{children}</AuthProvider>;
}
