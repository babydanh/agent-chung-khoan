# Blockers (supabase-ci)
- Push of `.github/workflows/db-test.yml` rejected: token has no `workflow` scope. File is at `ci-pending/workflows/db-test.yml`;
  a person with the scope should `git mv ci-pending/workflows/db-test.yml .github/workflows/` and push.
- Not verified: `supabase start` / `supabase db reset` with the real CLI (needs many images; workflow and supabase/config.toml untested), real Supabase auth schema.
