# Supabase User Sync Setup

## Step 1: Run the SQL Trigger in Supabase Dashboard

Go to your Supabase Dashboard → SQL Editor and run the following SQL:

```sql
-- Create a function that will be called when a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public."user" (id, email, hashed_password, is_active, created_at)
  VALUES (
    NEW.id,
    NEW.email,
    '', -- Empty string for OAuth users (no password)
    true,
    NOW()
  )
  ON CONFLICT (id) DO NOTHING; -- Prevent duplicates if user already exists
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create the trigger on auth.users table
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- Backfill existing Supabase auth users into the user table
INSERT INTO public."user" (id, email, hashed_password, is_active, created_at)
SELECT 
  id,
  email,
  '' as hashed_password,  -- Empty for all users (OAuth don't have passwords)
  true as is_active,
  created_at
FROM auth.users
ON CONFLICT (id) DO NOTHING;
```

## What This Does:

1. **Creates a trigger function** that automatically inserts a record into your `user` table whenever someone signs up via Supabase Auth (email/password or OAuth)

2. **Sets up the trigger** to fire after each new user is created in `auth.users`

3. **Backfills existing users** - If you already have users who signed in before,this will add them to your `user` table

## Verify It Worked:

After running the SQL, test by:
1. Sign in with Google on your app
2. Check the `user` table in Supabase - you should see a new record with:
   - `id`: matches the auth.users.id
   - `email`: your Google email
   - `hashed_password`: empty string
   - `is_active`: true

## Testing the Trigger:

```sql
-- View all users in your custom user table
SELECT id, email, hashed_password, is_active, created_at 
FROM public."user";

-- Compare with Supabase auth users
SELECT id, email, created_at 
FROM auth.users;
```

Both queries should show the same users (by id and email).
