-- Owner requested email/password sign-in without mandatory authenticator enrollment.
create or replace function private.actor() returns text language plpgsql stable security definer set search_path = '' as $$
declare actor_id uuid := auth.uid();
begin
  if actor_id is null
    or not exists(select 1 from auth.users u where u.id=actor_id and u.email_confirmed_at is not null)
    or exists(select 1 from private.revoked_sessions r where r.session_id::text=auth.jwt()->>'session_id')
    or not exists(select 1 from auth.sessions s where s.id::text=auth.jwt()->>'session_id' and s.user_id=actor_id
                  and (s.not_after is null or s.not_after > now())) then
    raise exception 'Verified sign-in required' using errcode='42501';
  end if;
  return actor_id::text;
end $$;
