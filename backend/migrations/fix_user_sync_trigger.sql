-- FIX: Only sync user to public table when email is verified
-- Drop the old trigger that fired blindly on INSERT
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  -- Only create/update the user if their email is confirmed
  -- OAuth users typically have this set immediately.
  -- Email signups have this set only after clicking the link.
  IF NEW.email_confirmed_at IS NOT NULL THEN
      INSERT INTO public."user" (id, email, hashed_password, is_active, created_at)
      VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.encrypted_password, ''),
        true, -- Now we know they are active/verified
        NEW.created_at
      )
      ON CONFLICT (id) DO UPDATE
      SET 
        email = EXCLUDED.email,
        is_active = true,
        hashed_password = EXCLUDED.hashed_password;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Re-create trigger for INSERT (handles OAuth / pre-verified users)
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- Create trigger for UPDATE (handles Email Verification flow)
DROP TRIGGER IF EXISTS on_auth_user_updated ON auth.users;
CREATE TRIGGER on_auth_user_updated
  AFTER UPDATE ON auth.users
  FOR EACH ROW
  WHEN (OLD.email_confirmed_at IS NULL AND NEW.email_confirmed_at IS NOT NULL)
  EXECUTE FUNCTION public.handle_new_user();
