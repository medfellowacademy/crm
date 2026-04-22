-- Fix NULL created_at and updated_at values in users table
-- Run this directly in Supabase SQL editor

UPDATE users
SET created_at = NOW()
WHERE created_at IS NULL;

UPDATE users
SET updated_at = NOW()
WHERE updated_at IS NULL;

-- Verify the fix
SELECT
    COUNT(*) as total_users,
    COUNT(created_at) as users_with_created_at,
    COUNT(updated_at) as users_with_updated_at
FROM users;

-- Show any remaining NULL values
SELECT id, full_name, email, created_at, updated_at
FROM users
WHERE created_at IS NULL OR updated_at IS NULL;
