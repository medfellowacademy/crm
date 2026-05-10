-- Reset users table: delete all existing users and insert single Super Admin
-- Run this directly in Supabase SQL editor

-- Step 1: Clear dependent foreign keys first (reports_to self-ref)
UPDATE public.users SET reports_to = NULL;

-- Step 2: Delete all existing users
DELETE FROM public.users;

-- Step 3: Reset the ID sequence so IDs start from 1
ALTER SEQUENCE public.users_id_seq RESTART WITH 1;

-- Step 4: Insert Super Admin
INSERT INTO public.users (full_name, email, phone, password, role, reports_to, is_active, created_at, updated_at)
VALUES (
    'Santhosh Reddy',
    'santhosh@medfellow.in',
    '8220952369',
    '$2b$12$sU1tBXnBXVeFGYnGAZyfXOuax2f35GFA7LYOQ72CWihqKZBPltkym',
    'Super Admin',
    NULL,
    TRUE,
    NOW(),
    NOW()
);

-- Step 5: Verify
SELECT id, full_name, email, phone, role, is_active FROM public.users;
