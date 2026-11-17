BEGIN;
-- Phase 6 (C14): photo-generator assets, outreach messages and the suppression list.
CREATE TABLE photo_assets (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id      uuid REFERENCES tasks(id),
  direction_id uuid NOT NULL REFERENCES design_directions(id),
  sha256       text NOT NULL,
  path         text NOT NULL,
  width        int NOT NULL CHECK (width BETWEEN 16 AND 4096),
  height       int NOT NULL CHECK (height BETWEEN 16 AND 4096),
  params       jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outreach_suppressions (
  address    text PRIMARY KEY CHECK (address = lower(address)),
  reason     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outreach_messages (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id     uuid REFERENCES tasks(id),
  agent_id    uuid REFERENCES agents(id),
  to_address  text NOT NULL CHECK (to_address = lower(to_address)),
  subject     text NOT NULL,
  body        text NOT NULL,
  status      text NOT NULL CHECK (status IN ('draft','held','sent','suppressed')),
  approval_id uuid REFERENCES approvals(id),
  note        text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outreach_by_recipient ON outreach_messages (to_address, created_at);

GRANT SELECT, INSERT ON photo_assets TO revenueos_app;
GRANT SELECT, INSERT, UPDATE ON outreach_messages TO revenueos_app;
GRANT SELECT, INSERT ON outreach_suppressions TO revenueos_app;
COMMIT;
