-- Enable Row Level Security on all application tables exposed in public schema.
--
-- Why: Supabase exposes public tables via PostgREST. Without RLS, the anon/authenticated
-- roles could read or write data directly. This app routes all data access through
-- the FastAPI backend (postgres role), which bypasses RLS.
--
-- Run in Supabase → SQL Editor, or: psql $DATABASE_URL -f enable_rls.sql

-- Application tables (created by setup_db / SQLModel)
-- Note: "user" is a reserved word — must be quoted
ALTER TABLE public."user"              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notebook            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chatmessage         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messagecitation     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.generatedcontent    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.task_progress       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.googleoauthtoken    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.feedback            ENABLE ROW LEVEL SECURITY;

-- Procrastinate task queue tables (if present)
ALTER TABLE IF EXISTS public.procrastinate_jobs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.procrastinate_events         ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.procrastinate_periodic_defers ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owner when not superuser (defense in depth)
ALTER TABLE public."user"              FORCE ROW LEVEL SECURITY;
ALTER TABLE public.notebook            FORCE ROW LEVEL SECURITY;
ALTER TABLE public.document            FORCE ROW LEVEL SECURITY;
ALTER TABLE public.chatmessage         FORCE ROW LEVEL SECURITY;
ALTER TABLE public.messagecitation     FORCE ROW LEVEL SECURITY;
ALTER TABLE public.generatedcontent    FORCE ROW LEVEL SECURITY;
ALTER TABLE public.task_progress       FORCE ROW LEVEL SECURITY;
ALTER TABLE public.googleoauthtoken    FORCE ROW LEVEL SECURITY;
ALTER TABLE public.feedback            FORCE ROW LEVEL SECURITY;

-- No permissive policies for anon/authenticated → direct PostgREST access is blocked.
-- Backend (postgres role) and SECURITY DEFINER triggers still work normally.
