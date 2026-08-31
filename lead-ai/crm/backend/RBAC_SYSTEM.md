# RBAC System

Central implementation: **`rbac.py`** (backend) + **`src/config/rbac.js`** (frontend).
They share the same permission names. `rbac.py` is authoritative; the frontend
only hides/shows UI and now hydrates its permission list from
`GET /api/auth/me`.

## Golden rules

1. **Live role, never the token.** Every authorization decision resolves the
   user's role from the database on each request (`get_current_user` /
   `rbac.current_user`). A demotion, promotion or deactivation takes effect on
   the **next request** — no waiting for the 24 h JWT to expire.
2. **Fail closed.** Unknown role → no permissions. Missing `is_active` false →
   locked out. Webhook with no signing secret configured → rejected (503).
3. **One choke point.** Use the dependencies from `rbac.py`. Do not hand-roll
   `if user["role"] == "...":` in new endpoints.

## Roles & hierarchy (rank)

| Role         | Rank | Summary |
|--------------|------|---------|
| Super Admin  | 100  | Everything, incl. user management, roles, settings, audit, cache |
| Manager      | 80   | All leads + assign, all WhatsApp, team analytics, all revenue, view users |
| Team Leader  | 60   | Same as Manager (team-lead scope) |
| Finance      | 40   | All leads (read), all revenue, payments, financial export, analytics. **No WhatsApp. No user mgmt.** |
| Marketing    | 40   | All leads (read), analytics + team analytics, report export. **No revenue, no editing, no WhatsApp.** |
| Counselor    | 20   | **Own** leads only, **own** WhatsApp, create/edit leads, revenue view, analytics |

Rank is used for user-administration guard-rails: a non-Super-Admin can only
act on a role **strictly below** their own and can never grant a role at or
above their own rank (no self-escalation, no peer promotion). The last active
Super Admin cannot be demoted / deactivated / deleted.

## Permission → role matrix

Mirrors `src/config/rbac.js`. Key entries:

| Permission | Super Admin | Manager | Team Leader | Finance | Marketing | Counselor |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| view_all_leads | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| view_own_leads | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| create_lead / edit_lead | ✅ | ✅ | ✅ | — | — | ✅ |
| delete_lead | ✅ | — | — | — | — | — |
| assign_lead | ✅ | ✅ | ✅ | — | — | — |
| view_all_whatsapp | ✅ | ✅ | ✅ | — | — | — |
| view_own_whatsapp / send_whatsapp | ✅ | ✅ | ✅ | — | — | ✅ |
| view_users | ✅ | ✅ | ✅ | — | — | — |
| create_user / edit_user / delete_user | ✅ | — | — | — | — | — |
| view_revenue | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| view_all_revenue | ✅ | ✅ | ✅ | ✅ | — | — |
| manage_payments / export_financial_data | ✅ | — | — | ✅ | — | — |
| view_analytics | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| view_team_analytics | ✅ | ✅ | ✅ | — | ✅ | — |
| export_reports | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| manage_settings / view_audit_logs / manage_roles | ✅ | — | — | — | — | — |

## Using it in an endpoint

```python
from rbac import require_permission, require_min_rank, require_super_admin, P

# permission gate as a route dependency (no handler arg needed)
@app.get("/api/admin/thing", dependencies=[Depends(require_permission(P.VIEW_TEAM_ANALYTICS))])
async def thing(): ...

# permission gate that also gives you the live user
@app.post("/api/leads/{lead_id}/note")
async def add(lead_id: str, actor: dict = Depends(require_permission(P.EDIT_LEAD))):
    lead = supabase_data.get_lead_by_id(lead_id)
    assert_can_view_lead(actor, lead)   # counselor row-level check
    ...

# hierarchy gate
@app.post("/api/x", dependencies=[Depends(require_min_rank(ROLE_MANAGER))])
```

Row-level lead isolation: `scope_supabase_leads(query, user)` on list queries,
`assert_can_view_lead(user, lead)` / `assert_can_edit_lead(user, lead)` on
single-lead routes. Ownership is matched on the assigned counselor's **full
name**, case-insensitively (that is what every write path stores in
`leads.assigned_to`).

## Webhooks

`/api/whatsapp/webhook` and `/api/interakt/webhook` are public (the provider
has no CRM JWT) but the **raw body is HMAC-verified**:

| Env var | Purpose |
|---|---|
| `META_APP_SECRET` | Meta `X-Hub-Signature-256` verification. **Required** or the webhook returns 503. |
| `INTERAKT_WEBHOOK_SECRET` | Interakt signature / shared-secret header. **Required** or 503. |
| `META_WHATSAPP_WEBHOOK_VERIFY_TOKEN` | GET verify-handshake token (constant-time compared). |
| `ALLOW_UNSIGNED_WEBHOOKS=true` | Escape hatch: accept unsigned webhooks with a loud warning. Do not use in production. |

## New endpoint

`GET /api/auth/me` → live `{ id, full_name, email, role, is_active,
reports_to, departments, page_grants, rank, permissions[] }`. The frontend
calls this on load / token change and drives all `hasPermission()` checks
from `permissions[]`.

## Recommended follow-up (not done here)

`leads.assigned_to` stores a display name. Add `leads.assigned_to_id bigint
references users(id)`, backfill, and switch the four functions at the top of
`rbac.py` (`counselor_scope_name`, `scope_supabase_leads`, `can_view_lead`) to
compare on user id. Nothing else needs to change.
