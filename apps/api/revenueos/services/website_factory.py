"""Generate real, buildable, static Next.js websites; no invented claims or stock photos."""
import io
import json
import re
import zipfile
from html import escape as html_escape


def site_zip(company: str, industry: str, tagline: str, email: str, city: str, services: list[str]) -> bytes:
    def js(s: str) -> str:
        return json.dumps(s).replace("<", "\\u003c").replace(">", "\\u003e")
    slug = re.sub(r"[^a-z0-9-]", "-", company.lower()).strip("-")[:60] or "business-site"
    items = ",".join(js(s) for s in services)
    root = f"{slug}/"
    data = {
        "package.json": json.dumps({"name": slug, "version": "1.0.0", "private": True, "scripts": {"dev": "next dev", "build": "next build"}, "dependencies": {"next": "^16.0.0", "react": "^19.2.0", "react-dom": "^19.2.0", "lucide-react": "^0.468.0"}, "devDependencies": {"typescript": "^5.8.0", "@types/react": "^19.0.0", "@types/node": "^22.0.0"}}, indent=2),
        "next.config.ts": 'import type { NextConfig } from "next";\nconst nextConfig: NextConfig = { output: "export", reactStrictMode: true };\nexport default nextConfig;\n',
        "tsconfig.json": json.dumps({"compilerOptions": {"target": "ES2017", "lib": ["dom", "dom.iterable", "esnext"], "allowJs": True, "skipLibCheck": True, "strict": True, "noEmit": True, "esModuleInterop": True, "module": "esnext", "moduleResolution": "bundler", "resolveJsonModule": True, "isolatedModules": True, "jsx": "react-jsx", "incremental": True, "plugins": [{"name": "next"}]}, "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"], "exclude": ["node_modules"]}, indent=2),
        "next-env.d.ts": '/// <reference types="next" />\n/// <reference types="next/image-types/global" />\n',
        "app/layout.tsx": f'''import type {{ Metadata }} from "next";\nimport "./globals.css";\nexport const metadata: Metadata = {{ title: {js(company)}, description: {js(tagline)} }};\nexport default function Layout({{children}}:Readonly<{{children:React.ReactNode}}>) {{ return <html lang="en"><body>{{children}}</body></html> }}\n''',
        "app/page.tsx": f'''const company = {js(company)};\nconst tagline = {js(tagline)};\nconst city = {js(city)};\nconst services = [{items}];\nconst email = {js(email)};\nexport default function Home() {{ return <><header><strong>{{company}}</strong><nav><a href="#services">Services</a><a href="#about">About</a><a href="#contact">Contact</a></nav></header><main><section className="hero"><p className="eyebrow">Serving {{city}}</p><h1>{{tagline}}</h1><p>Explore our services and contact our team to discuss your requirements.</p><a className="button" href={{`mailto:${{email}}?subject=Service%20inquiry`}}>Request a quote</a></section><section id="services"><p className="eyebrow">What we offer</p><h2>Our services</h2><div className="cards">{{services.map((s)=><article key={{s}}><h3>{{s}}</h3><p>Contact our team to ask about service details and availability.</p></article>)}}</div></section><section id="about"><p className="eyebrow">About</p><h2>{{company}}</h2><p>We serve inquiries in {{city}}. Contact us to confirm service coverage, credentials, pricing and scheduling.</p></section><section id="contact"><p className="eyebrow">Get in touch</p><h2>Start a conversation</h2><p><a href={{`mailto:${{email}}`}}>{{email}}</a></p></section></main><footer>© {{new Date().getFullYear()}} {{company}}. Information and service availability must be confirmed by the business.</footer></> }}\n''',
        "app/globals.css": '''*{box-sizing:border-box}body{margin:0;background:#f8fafc;color:#111827;font-family:system-ui,-apple-system,Segoe UI,sans-serif}header{display:flex;align-items:center;justify-content:space-between;padding:1.5rem max(5%,calc((100vw - 1100px)/2));background:white;gap:1rem}nav{display:flex;gap:1rem;flex-wrap:wrap}a{color:#156f66}main{max-width:1100px;margin:auto;padding:0 5%}.hero{padding:7rem 0;min-height:60vh}h1{font-size:clamp(2.4rem,7vw,5rem);letter-spacing:-.055em;max-width:900px;line-height:1.08;margin:.3em 0}h2{font-size:clamp(1.7rem,4vw,3rem);letter-spacing:-.03em}p{line-height:1.65;color:#475569;max-width:64ch}.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:.8rem;font-weight:700;color:#047857}.button{display:inline-block;background:#047857;color:white;padding:.95rem 1.5rem;border-radius:12px;text-decoration:none;font-weight:700;margin-top:1rem}section{scroll-margin-top:2rem;padding:3rem 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}.cards article{background:white;padding:1.5rem;border-radius:14px;box-shadow:0 8px 24px #0f172a10}footer{padding:2rem 5%;border-top:1px solid #e2e8f0;text-align:center;color:#64748b;font-size:.8rem}@media(max-width:600px){header{align-items:flex-start;flex-direction:column}.hero{padding:4rem 0;min-height:auto}}''',
        "README.md": f"# {company} — static website\n\nIndustry: {industry}. Generated as editable source code. No vendor lock-in.\n\n## Run\n\n```bash\nnpm install\nnpm run dev\n```\n\nFor production: `npm run build` creates `out/`, deploy to a static host. Configure a real domain, forms, privacy notice, licensing statements and company-owned imagery before publishing. No externally callable backend or contact form is included; contact links open an email client. Generated content should be reviewed and approved before deployment.\n",
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path, content in data.items():
            z.writestr(root + path, content)
    return out.getvalue()
