# Auth + Owned Profile Architecture Notes

## What changed in this session

- Added a new Alembic migration: `backend/alembic/versions/0004_auth_user_and_ownership.py`
  - `tbl_user_account` — authentication identity (email, password hash, provider)
  - `tbl_user_role` — role membership, starting with `CITIZEN` and `ADMIN`
  - `tbl_user_session` — server-side token/session rows
  - `owning_user_id` FK on `tbl_citizen_master`
- Added auth models in `backend/app/models/auth.py`
- Added auth repository in `backend/app/repositories/auth_repository.py`
- Added auth service in `backend/app/services/auth_service.py`
- Added auth API in `backend/app/api/v1/auth.py`
  - `POST /auth/register`
  - `POST /auth/login`
  - `GET /auth/me`
  - `POST /auth/logout`
- Wired auth into the v1 router
- Updated citizen repository to support owned profile creation and lookup
- Updated frontend:
  - `frontend/src/services/auth.js`
  - `frontend/src/pages/auth/LoginPage.jsx`
  - `frontend/src/pages/auth/RegisterPage.jsx`
  - `frontend/src/components/auth/AuthGate.jsx`
  - `frontend/src/components/auth/AuthLayout.jsx`
  - `frontend/src/components/layout/Header.jsx`
  - `frontend/src/App.jsx`
  - `frontend/src/services/api.js`
  - `frontend/vite.config.js`

## Current behavior

- Public pages:
  - Home page is still visible to everyone (scheme catalogue).
  - Schemes, scheme detail, explore, help remain usable.
- Auth flow:
  - Register creates the account and the owned citizen profile in one step.
  - Login issues a token.
  - The frontend stores the token and the current user locally for this session.
  - Authenticated routes show the header account menu and support sign out.

## Planned behavior we still want to enforce

- Profile completion gating:
  - After login, a user can view the homepage even if they skipped the long profile form.
  - Before any eligibility check, the app should prompt the user to complete their profile if it is missing.
- Eligibility and recommendations should use the authenticated user’s owned profile, not a client-supplied citizen id.

## Migration and run plan

1. From the project’s own backend environment with DATABASE_URL configured:
   - Run `alembic upgrade head` to apply `0004_auth_user_and_ownership`.
2. Run the backend dev server from the project’s own environment.
3. Run the frontend dev server from its own environment.
4. Verify:
   - Register creates an account and a citizen profile owned by that account.
   - Login returns a token.
   - `/auth/me` returns the current user.
   - Logout invalidates the token.
   - Homepage is still reachable by anonymous users.
   - After login, the user can reach the profile page and edit their owned profile.
5. After that, retest the existing eligibility/form flows from the project’s own runtime.

## Things to watch

- Do not run `alembic downgrade` unless you know the current database state.
- The auth code was written to be structurally correct in this environment, but the real validation happens when the project runtime starts and hits the database.
- If the existing seed data does not have `owning_user_id` yet, that is fine; new authenticated users will own new profiles. Old rows can be linked later if needed.
