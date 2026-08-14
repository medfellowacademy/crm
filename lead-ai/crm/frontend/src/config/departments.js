// ─────────────────────────────────────────────────────────────────────────────
// Departments — single source of truth for how the app's ~24 pages group into
// business departments. Used by:
//   • DepartmentsPage  — the card-grid hub (click a department → its pages)
//   • ProfessionalLayout — the sidebar renders one collapsible group per
//     department the user can access, instead of a flat 24-item list
//   • UsersPage — the "Department Access" multi-select when creating/editing
//     a user writes these keys to users.departments (jsonb)
//
// Access model:
//   • Super Admin always sees every department.
//   • If a user has explicit `departments` grants, those win.
//   • Otherwise the role's DEFAULT_ROLE_DEPARTMENTS below apply, matching the
//     pre-existing role-based visibility so nobody loses pages on upgrade.
//   • GENERAL_PAGES are visible to everyone regardless of department.
//   • ADMIN_ONLY_PAGES stay Super Admin-only even inside a granted department.
// ─────────────────────────────────────────────────────────────────────────────
import {
  LayoutDashboard, Users, Hospital, BookOpen, BarChart3, TrendingUp,
  GitBranch, UserPlus, Activity, Shield, CalendarClock, DollarSign,
  Settings, Timer, Users2, ClipboardList,
  Share2, Globe, Bot, Trophy, MapPin, Building2, Megaphone, Wallet,
  Settings2,
} from 'lucide-react';

export const DEPARTMENTS = {
  sales: {
    key: 'sales',
    name: 'Sales',
    icon: TrendingUp,
    color: '#10b981',
    description: 'Leads, pipeline, follow-ups and counselor performance',
    pages: [
      { key: '/leads',            icon: Users,         label: 'Leads' },
      { key: '/pipeline',         icon: GitBranch,     label: 'Pipeline' },
      { key: '/followups',        icon: CalendarClock, label: "Today's Follow-ups" },
      { key: '/lead-analysis',    icon: TrendingUp,    label: 'Lead Analysis' },
      { key: '/team-performance', icon: Trophy,        label: 'Team Performance' },
      { key: '/conversion-time',  icon: Timer,         label: 'Conversion Time' },
      { key: '/cohort-analysis',  icon: Users2,        label: 'Cohort Analysis' },
    ],
  },
  marketing: {
    key: 'marketing',
    name: 'Marketing',
    icon: Megaphone,
    color: '#fa8c16',
    description: 'Lead sources, campaigns, and channel attribution',
    pages: [
      { key: '/meta-leads',    icon: Share2,    label: 'Meta Leads' },
      { key: '/website-leads', icon: Globe,     label: 'Website Leads' },
      { key: '/analytics',     icon: BarChart3, label: 'Analytics' },
    ],
  },
  finance: {
    key: 'finance',
    name: 'Finance',
    icon: Wallet,
    color: '#13c2c2',
    description: 'Revenue, payments, EMIs and outstanding balances',
    pages: [
      { key: '/payments',  icon: DollarSign, label: 'Payments' },
      { key: '/analytics', icon: BarChart3,  label: 'Analytics' },
    ],
  },
  operations: {
    key: 'operations',
    name: 'Operations',
    icon: Settings2,
    color: '#8b5cf6',
    description: 'Courses, hospitals, attendance and activity tracking',
    pages: [
      { key: '/hospitals',            icon: Hospital,      label: 'Hospitals' },
      { key: '/courses',              icon: BookOpen,      label: 'Courses' },
      { key: '/attendance',           icon: MapPin,        label: 'Attendance' },
      { key: '/user-activity',        icon: Activity,      label: 'User Activity' },
      { key: '/lead-update-activity', icon: ClipboardList, label: 'Lead Updates' },
    ],
  },
  administration: {
    key: 'administration',
    name: 'Administration',
    icon: Shield,
    color: '#ff4d4f',
    description: 'User accounts, access control and audit trail',
    pages: [
      { key: '/users',      icon: UserPlus, label: 'Team' },
      { key: '/audit-logs', icon: Shield,   label: 'Audit Logs' },
    ],
  },
};

export const DEPARTMENT_OPTIONS = Object.values(DEPARTMENTS).map(d => ({
  value: d.key,
  label: d.name,
}));

// Pages every authenticated user sees regardless of department grants.
export const GENERAL_PAGES = [
  { key: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard' },
  { key: '/departments', icon: Building2,       label: 'Departments' },
  { key: '/ai-chat',     icon: Bot,             label: 'MedFellow AI Chat' },
  { key: '/settings',    icon: Settings,        label: 'Settings' },
];

// Pages counselors need day-to-day even though they belong to Sales/Finance
// department groups — counselors keep them without any department grant.
export const COUNSELOR_PAGES = ['/attendance', '/followups', '/leads', '/pipeline', '/payments', '/lead-update-activity'];

// Even inside a granted department, these remain Super Admin-only.
export const ADMIN_ONLY_PAGES = ['/users', '/audit-logs'];

// When a user has NO explicit department grants, fall back to what their
// role could already see before department-based access existed.
export const DEFAULT_ROLE_DEPARTMENTS = {
  'Super Admin': ['sales', 'marketing', 'finance', 'operations', 'administration'],
  'Manager':     ['sales', 'marketing', 'finance', 'operations'],
  'Team Leader': ['sales', 'marketing', 'finance', 'operations'],
  'Finance':     ['finance'],
  'Marketing':   ['marketing'],
  'Counselor':   [],
};

// The department keys a given user may access.
export const userDepartments = (user) => {
  if (!user) return [];
  if (user.role === 'Super Admin') return Object.keys(DEPARTMENTS);
  const explicit = Array.isArray(user.departments) ? user.departments.filter(d => DEPARTMENTS[d]) : [];
  if (explicit.length > 0) return explicit;
  return DEFAULT_ROLE_DEPARTMENTS[user.role] || [];
};

// All page routes a user may open, considering department grants, role,
// counselor day-to-day pages and admin-only restrictions.
// If user.page_grants is non-empty, it acts as an allow-list: only those
// specific pages are accessible within the user's departments.
export const userAccessiblePages = (user) => {
  const routes = new Set(GENERAL_PAGES.map(p => p.key));
  if (user?.role === 'Counselor') COUNSELOR_PAGES.forEach(r => routes.add(r));

  const pageGrants = Array.isArray(user?.page_grants) && user.page_grants.length > 0
    ? new Set(user.page_grants)
    : null; // null = no restriction

  userDepartments(user).forEach(deptKey => {
    DEPARTMENTS[deptKey].pages.forEach(p => {
      if (ADMIN_ONLY_PAGES.includes(p.key) && user?.role !== 'Super Admin') return;
      if (pageGrants && !pageGrants.has(p.key)) return; // page-level restriction
      routes.add(p.key);
    });
  });
  return routes;
};
