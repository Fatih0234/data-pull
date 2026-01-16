-- Disable RLS and grant permissions for import
-- Run this in Supabase SQL Editor to allow the import script to work

-- Disable Row Level Security (since you want backend-only access)
ALTER TABLE events DISABLE ROW LEVEL SECURITY;

-- Grant INSERT permission to anon role (for import)
GRANT INSERT, SELECT, UPDATE, DELETE ON events TO anon;
GRANT INSERT, SELECT, UPDATE, DELETE ON events TO authenticated;

-- Verify permissions
SELECT
    grantee,
    privilege_type
FROM information_schema.role_table_grants
WHERE table_name = 'events';
