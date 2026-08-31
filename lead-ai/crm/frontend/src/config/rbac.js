// RBAC Configuration
// Role values must match exactly what the backend stores in the database
export const ROLES = {
  ADMIN: 'Super Admin',
  COUNSELLOR: 'Counselor',
  MANAGER: 'Manager',
  TEAM_LEADER: 'Team Leader',
  // Was 'finance' (lowercase) — never matched any value UsersPage could
  // actually assign ('Finance' wasn't even an option there), so the Finance
  // dashboard route was dead code. Fixed casing to match every other role
  // string, and Finance/Marketing are now real, assignable roles.
  FINANCE: 'Finance',
  MARKETING: 'Marketing',
};

export const PERMISSIONS = {
  // Lead permissions
  VIEW_ALL_LEADS: 'view_all_leads',
  VIEW_OWN_LEADS: 'view_own_leads',
  CREATE_LEAD: 'create_lead',
  EDIT_LEAD: 'edit_lead',
  DELETE_LEAD: 'delete_lead',
  ASSIGN_LEAD: 'assign_lead',

  // WhatsApp permissions
  VIEW_OWN_WHATSAPP: 'view_own_whatsapp',   // Counselors: own assigned leads only
  VIEW_ALL_WHATSAPP: 'view_all_whatsapp',   // Managers/Admin: all conversations
  SEND_WHATSAPP: 'send_whatsapp',           // Can send messages

  // User permissions
  VIEW_USERS: 'view_users',
  CREATE_USER: 'create_user',
  EDIT_USER: 'edit_user',
  DELETE_USER: 'delete_user',

  // Financial permissions
  VIEW_REVENUE: 'view_revenue',
  VIEW_ALL_REVENUE: 'view_all_revenue',
  MANAGE_PAYMENTS: 'manage_payments',
  EXPORT_FINANCIAL_DATA: 'export_financial_data',

  // Analytics permissions
  VIEW_ANALYTICS: 'view_analytics',
  VIEW_TEAM_ANALYTICS: 'view_team_analytics',
  EXPORT_REPORTS: 'export_reports',

  // System permissions
  MANAGE_SETTINGS: 'manage_settings',
  VIEW_AUDIT_LOGS: 'view_audit_logs',
  MANAGE_ROLES: 'manage_roles',
};

export const rolePermissions = {
  [ROLES.ADMIN]: [
    // Full access
    PERMISSIONS.VIEW_ALL_LEADS,
    PERMISSIONS.VIEW_OWN_LEADS,
    PERMISSIONS.CREATE_LEAD,
    PERMISSIONS.EDIT_LEAD,
    PERMISSIONS.DELETE_LEAD,
    PERMISSIONS.ASSIGN_LEAD,
    PERMISSIONS.VIEW_ALL_WHATSAPP,
    PERMISSIONS.SEND_WHATSAPP,
    PERMISSIONS.VIEW_USERS,
    PERMISSIONS.CREATE_USER,
    PERMISSIONS.EDIT_USER,
    PERMISSIONS.DELETE_USER,
    PERMISSIONS.VIEW_REVENUE,
    PERMISSIONS.VIEW_ALL_REVENUE,
    PERMISSIONS.MANAGE_PAYMENTS,
    PERMISSIONS.EXPORT_FINANCIAL_DATA,
    PERMISSIONS.VIEW_ANALYTICS,
    PERMISSIONS.VIEW_TEAM_ANALYTICS,
    PERMISSIONS.EXPORT_REPORTS,
    PERMISSIONS.MANAGE_SETTINGS,
    PERMISSIONS.VIEW_AUDIT_LOGS,
    PERMISSIONS.MANAGE_ROLES,
  ],

  [ROLES.COUNSELLOR]: [
    // Limited to own leads and own WhatsApp conversations
    PERMISSIONS.VIEW_OWN_LEADS,
    PERMISSIONS.CREATE_LEAD,
    PERMISSIONS.EDIT_LEAD,
    PERMISSIONS.VIEW_OWN_WHATSAPP,
    PERMISSIONS.SEND_WHATSAPP,
    PERMISSIONS.VIEW_REVENUE,
    PERMISSIONS.VIEW_ANALYTICS,
  ],

  [ROLES.MANAGER]: [
    // Team management — sees all WhatsApp conversations
    PERMISSIONS.VIEW_ALL_LEADS,
    PERMISSIONS.CREATE_LEAD,
    PERMISSIONS.EDIT_LEAD,
    PERMISSIONS.ASSIGN_LEAD,
    PERMISSIONS.VIEW_ALL_WHATSAPP,
    PERMISSIONS.SEND_WHATSAPP,
    PERMISSIONS.VIEW_USERS,
    PERMISSIONS.VIEW_ALL_REVENUE,
    PERMISSIONS.VIEW_TEAM_ANALYTICS,
    PERMISSIONS.EXPORT_REPORTS,
  ],

  [ROLES.TEAM_LEADER]: [
    // Team lead — sees all WhatsApp conversations
    PERMISSIONS.VIEW_ALL_LEADS,
    PERMISSIONS.CREATE_LEAD,
    PERMISSIONS.EDIT_LEAD,
    PERMISSIONS.ASSIGN_LEAD,
    PERMISSIONS.VIEW_ALL_WHATSAPP,
    PERMISSIONS.SEND_WHATSAPP,
    PERMISSIONS.VIEW_USERS,
    PERMISSIONS.VIEW_ALL_REVENUE,
    PERMISSIONS.VIEW_TEAM_ANALYTICS,
    PERMISSIONS.EXPORT_REPORTS,
  ],

  [ROLES.FINANCE]: [
    // Financial focus — no WhatsApp access
    PERMISSIONS.VIEW_ALL_LEADS,
    PERMISSIONS.VIEW_ALL_REVENUE,
    PERMISSIONS.MANAGE_PAYMENTS,
    PERMISSIONS.EXPORT_FINANCIAL_DATA,
    PERMISSIONS.VIEW_ANALYTICS,
  ],

  [ROLES.MARKETING]: [
    // Lead-generation focus — source/campaign attribution, no revenue
    // management and no per-lead editing (that's Sales' job).
    PERMISSIONS.VIEW_ALL_LEADS,
    PERMISSIONS.VIEW_ANALYTICS,
    PERMISSIONS.VIEW_TEAM_ANALYTICS,
    PERMISSIONS.EXPORT_REPORTS,
  ],
};

// The live permission list from GET /api/auth/me. When set, it is the source
// of truth (it reflects the user's CURRENT server-side role); the static
// role->permission map below is only the fallback for the brief window before
// /api/auth/me resolves.
let _serverPermissions = null;

export const setServerPermissions = (perms) => {
  _serverPermissions = Array.isArray(perms) ? perms : null;
};

export const getEffectivePermissions = (userRole) => {
  if (_serverPermissions) return _serverPermissions;
  return rolePermissions[userRole] || [];
};

export const hasPermission = (userRole, permission) => {
  // FAIL CLOSED: no known role and no server permission list => no access.
  if (!_serverPermissions && !userRole) return false;
  return getEffectivePermissions(userRole).includes(permission);
};

export const hasAnyPermission = (userRole, permissionList) => {
  return permissionList.some((permission) => hasPermission(userRole, permission));
};

export const hasAllPermissions = (userRole, permissionList) => {
  return permissionList.every((permission) => hasPermission(userRole, permission));
};

// Every guarded route -> the permission(s) that unlock it (any-of).
export const ROUTE_PERMISSIONS = {
  '/dashboard': [PERMISSIONS.VIEW_OWN_LEADS, PERMISSIONS.VIEW_ALL_LEADS],
  '/leads': [PERMISSIONS.VIEW_OWN_LEADS, PERMISSIONS.VIEW_ALL_LEADS],
  '/lead-analysis': [PERMISSIONS.VIEW_OWN_LEADS, PERMISSIONS.VIEW_ALL_LEADS],
  '/pipeline': [PERMISSIONS.VIEW_OWN_LEADS, PERMISSIONS.VIEW_ALL_LEADS],
  '/followups': [PERMISSIONS.VIEW_OWN_LEADS, PERMISSIONS.VIEW_ALL_LEADS],
  '/meta-leads': [PERMISSIONS.VIEW_ALL_LEADS],
  '/website-leads': [PERMISSIONS.VIEW_ALL_LEADS],
  '/users': [PERMISSIONS.VIEW_USERS],
  '/analytics': [PERMISSIONS.VIEW_ANALYTICS, PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/team-performance': [PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/conversion-time': [PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/cohort-analysis': [PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/source-analytics': [PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/sla': [PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/score-decay': [PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/user-activity': [PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/lead-update-activity': [PERMISSIONS.VIEW_AUDIT_LOGS, PERMISSIONS.VIEW_TEAM_ANALYTICS],
  '/payments': [PERMISSIONS.MANAGE_PAYMENTS, PERMISSIONS.VIEW_ALL_REVENUE],
  '/audit-logs': [PERMISSIONS.VIEW_AUDIT_LOGS],
  '/settings': [PERMISSIONS.MANAGE_SETTINGS],
};

// Routes that any authenticated user may open (app shell, profile, reference
// data). Anything not listed here AND not in ROUTE_PERMISSIONS is denied.
const PUBLIC_ROUTES = new Set([
  '/', '/login', '/logout', '/profile', '/unauthorized', '/dashboard',
  '/hospitals', '/courses', '/attendance', '/whatsapp',
]);

export const canAccessRoute = (userRole, route) => {
  if (!_serverPermissions && !userRole) return false; // fail closed
  const required = ROUTE_PERMISSIONS[route];
  if (required) return hasAnyPermission(userRole, required);
  if (PUBLIC_ROUTES.has(route)) return true;
  // Unknown route: allow only if the user has ANY lead-view permission
  // (i.e. is a real CRM user), never a blanket true.
  return hasAnyPermission(userRole, [PERMISSIONS.VIEW_OWN_LEADS, PERMISSIONS.VIEW_ALL_LEADS]);
};
