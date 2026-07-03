-- Trigger to sync Supabase auth.users to application user table
-- This ensures OAuth users are also saved to our custom user table

-- First, update the User table to make hashed_password nullable
-- since OAuth users don't have passwords
ALTER TABLE "user" ALTER COLUMN hashed_password DROP NOT NULL;

-- Create a function that will be called when a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public."user" (id, email, hashed_password, is_active, created_at)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.encrypted_password, ''), -- Use empty string for OAuth users
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
  COALESCE(encrypted_password, '') as hashed_password,
  true as is_active,
  created_at
FROM auth.users
ON CONFLICT (id) DO NOTHING;
