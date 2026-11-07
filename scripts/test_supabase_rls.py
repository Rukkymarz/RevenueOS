"""Run real Postgres permission tests in an isolated CI database, never a live project.

Auth tables/functions below are deliberately minimal Supabase-compatible test
fixtures. Live Supabase Auth, Storage service and MFA require separate acceptance.
"""
import json
import os
from pathlib import Path
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]


def main():
    url = os.environ["SUPABASE_TEST_DATABASE_URL"]
    if os.getenv("REVENUEOS_TEST_DATABASE") != "true" or conninfo_to_dict(url).get("dbname") != "revenueos_supabase_test":
        raise RuntimeError("Explicit disposable database required")
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("create role anon nologin; create role authenticated nologin;")
        db.execute("""
        create schema auth;
        create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
        create table auth.sessions(id uuid primary key,user_id uuid references auth.users,not_after timestamptz);
        create function auth.jwt() returns jsonb language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb$$;
        create function auth.uid() returns uuid language sql stable as $$select (auth.jwt()->>'sub')::uuid$$;
        grant usage on schema auth,public to authenticated,anon;
        grant execute on function auth.jwt(),auth.uid() to authenticated,anon;
        create schema storage;
        create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
        create table storage.objects(id uuid default gen_random_uuid(),bucket_id text,name text,owner_id text);
        alter table storage.objects enable row level security;
        grant usage on schema storage to authenticated;
        grant select,insert on storage.objects to authenticated;
        """)
        for migration in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            db.execute(migration.read_text(encoding="utf-8"))
        admin, other, viewer = [str(uuid.uuid4()) for _ in range(3)]
        sessions = {}
        for subject,email in [(admin,"owner@example.org"),(other,"other@example.org"),(viewer,"viewer@example.org")]:
            session = str(uuid.uuid4());sessions[subject]=session
            db.execute("insert into auth.users values(%s,%s,now())",(subject,email))
            db.execute("insert into auth.sessions values(%s,%s,null)",(session,subject))
        db.execute("insert into private.configuration values(true,'owner@example.org')")

        def query(subject,sql,parameters=(),aal="aal2",session=None):
            with db.transaction():
                db.execute("set local role authenticated")
                db.execute("select set_config('request.jwt.claims',%s,true)",(json.dumps({"sub":subject,"aal":aal,"session_id":session or sessions[subject]}),))
                return db.execute(sql,parameters).fetchall()

        def denied(subject,sql,parameters=(),**kwargs):
            try:
                query(subject,sql,parameters,**kwargs)
            except psycopg.Error:
                return
            raise AssertionError("Operation unexpectedly permitted")

        denied(other,"select public.revenueos_create_workspace('Wrong owner','services',true)")
        denied(admin,"select public.revenueos_create_workspace('First workspace','services',true)",aal="aal1")
        first=query(admin,"select public.revenueos_create_workspace('First workspace','services',true)")[0][0]["id"]
        second=query(admin,"select public.revenueos_create_workspace('Second workspace','services',false)")[0][0]["id"]
        query(admin,"select public.revenueos_add_member(%s,%s,%s,'operator')",(second,other,"other@example.org"))
        query(admin,"select public.revenueos_add_member(%s,%s,%s,'viewer')",(first,viewer,"viewer@example.org"))
        insert="""insert into public.leads(business_id,business_name,industry,stage,source,metrics,opted_out,grade,score_confidence)
                  values(%s,'Measured lead','services','new','manual','{"seo":35}',false,'Unscored',0) returning id,score,score_confidence"""
        lead,score,confidence=query(admin,insert,(first,))[0]
        assert (score,confidence)==(35,25)
        assert query(other,"select id from public.leads where business_id=%s",(first,))==[]
        denied(viewer,insert,(first,))
        denied(other,insert,(first,))
        denied(admin,"update public.leads set business_id=%s where id=%s returning id",(second,lead))
        denied(other,"insert into public.memberships(business_id,subject,email,role) values(%s,%s,'other@example.org','admin')",(first,other))
        denied(admin,"select * from public.leads",aal="aal1")
        denied(admin,"select * from public.leads",session=str(uuid.uuid4()))
        denied(other,"select public.revenueos_export(%s)",(first,))
        with db.transaction():
            db.execute("set local role anon")
            try:
                with db.transaction():db.execute("select * from public.leads")
            except psycopg.Error:pass
            else:raise AssertionError("Anonymous read permitted")
        query(admin,"update public.leads set email='recipient@example.org' where id=%s returning id",(lead,))
        draft=query(admin,"select public.revenueos_draft_email(%s,%s,'Approved scope','A real approved message body.')",(first,lead))[0][0]
        approval=draft["approval"]["id"]
        preview=query(admin,"select public.revenueos_review_email(%s,%s)",(first,approval))[0][0]
        denied(viewer,"select public.revenueos_review_email(%s,%s)",(first,approval))
        denied(admin,"select public.revenueos_review_email(%s,%s,'approved',%s)",(first,approval,"0"*64))
        result=query(admin,"select public.revenueos_review_email(%s,%s,'approved',%s)",(first,approval,preview["review_hash"]))[0][0]
        assert result["decision"]=="approved"
        denied(admin,"select public.revenueos_review_email(%s,%s,'rejected')",(first,approval))
        report=query(admin,"select public.revenueos_report(%s,true)",(first,))[0][0]
        assert report["lead_volume"]==1 and report["mrr"]==0
        denied(admin,"select public.revenueos_import_leads(%s,%s)",(first,json.dumps([{"business_name":"Atomic valid"},{"business_name":"x"}])))
        assert query(admin,"select count(*) from public.leads where business_id=%s",(first,))[0][0]==1
        job=query(admin,"select public.revenueos_reserve_media(%s,'image','Artifact title','Subtitle')",(first,))[0][0]
        denied(admin,"select public.revenueos_finish_media(%s,%s,true)",(first,job["id"]))
        query(admin,"insert into storage.objects(bucket_id,name,owner_id) values('revenueos-artifacts',%s,%s) returning name",(f"{first}/{admin}/{job['id']}.svg",admin))
        query(admin,"select public.revenueos_finish_media(%s,%s,true)",(first,job["id"]))
        assert query(other,"select name from storage.objects")==[]
        denied(other,"insert into storage.objects(bucket_id,name) values('revenueos-artifacts',%s) returning name",(f"{first}/{other}/arbitrary.svg",))
        assert query(admin,"select public.revenueos_export(%s)",(first,))[0][0]["records"]["leads"][0]["id"]==lead
        query(admin,"select public.revenueos_revoke_sessions()")
        denied(admin,"select * from public.leads")
        # Revoking the first actor must not revoke another workspace user's session.
        assert query(other,"select public.revenueos_report(%s,false)",(second,))[0][0]["lead_volume"]==0
    print("PASS: Supabase-compatible schema, MFA/session gates, RLS/RBAC, protected fields, approvals, atomic import and artifact isolation")


if __name__ == "__main__":
    main()
