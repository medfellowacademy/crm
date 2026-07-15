import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Drawer } from 'antd';
import {
  Users,
  ChevronLeft,
  ChevronDown,
  CalendarClock,
  GitBranch,
  DollarSign,
  MapPin,
  Search,
  LogOut,
  ClipboardList,
} from 'lucide-react';
import SmartNotifications from '../../features/notifications/SmartNotifications';
import { isFeatureEnabled } from '../../config/featureFlags';
import { authAPI, aiSearchAPI, leadsAPI, usersAPI, dashboardAPI, coursesAPI, systemAPI } from '../../api/api';
import {
  DEPARTMENTS, GENERAL_PAGES, COUNSELOR_PAGES, ADMIN_ONLY_PAGES, userDepartments,
} from '../../config/departments';


// Global Search Component
const SearchBar = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const navigate = useNavigate();

  const handleSearch = async (value) => {
    if (value.trim().length === 0) {
      setResults([]);
      setDrawerOpen(false);
      return;
    }

    setSearching(true);
    try {
      const response = await aiSearchAPI.search(value);
      setResults(response.data?.leads || []);
      setDrawerOpen(true);
    } catch (error) {
      console.error('Search error:', error);
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleResultClick = (leadId) => {
    navigate(`/leads/${leadId}`);
    setDrawerOpen(false);
    setQuery('');
  };

  return (
    <>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 16px',
        background: 'var(--bg-secondary)',
        borderRadius: 8,
        width: 320,
      }}>
        <Search size={16} style={{ color: 'var(--text-tertiary)' }} />
        <input
          type="text"
          placeholder="Search leads..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              handleSearch(query);
            }
          }}
          style={{
            border: 'none',
            background: 'transparent',
            outline: 'none',
            fontSize: 'var(--text-sm)',
            color: 'var(--text-primary)',
            width: '100%',
          }}
        />
      </div>

      <Drawer
        title="Search Results"
        placement="right"
        onClose={() => setDrawerOpen(false)}
        open={drawerOpen}
        width={400}
      >
        {searching ? (
          <div style={{ textAlign: 'center', padding: '24px' }}>
            <p>Searching...</p>
          </div>
        ) : results.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)' }}>
            {query ? 'No results found' : 'Enter a search query'}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {results.map((result) => (
              <motion.div
                key={result.lead_id}
                whileHover={{ x: 4 }}
                onClick={() => handleResultClick(result.lead_id)}
                style={{
                  padding: '12px',
                  background: 'var(--bg-secondary)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div style={{ fontWeight: '600', marginBottom: '4px' }}>
                  {result.full_name}
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  {result.course_interested || 'No course'}
                </div>
                {result.score && (
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                    Match score: {(result.score * 100).toFixed(0)}%
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </Drawer>
    </>
  );
};

const ProfessionalLayout = ({ children }) => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const initials = currentUser.full_name
    ? currentUser.full_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U';

  // ── Keep the Render backend warm while any user has the app open ──────────
  // Render free tier spins down after 15 min of inactivity.
  // Ping /health every 4 minutes so the server never cold-starts mid-session.
  useEffect(() => {
    // Immediate ping on mount so the server wakes up as soon as user logs in
    systemAPI.health().catch(() => {});
    const id = setInterval(() => {
      systemAPI.health().catch(() => {});
    }, 4 * 60 * 1000); // every 4 minutes
    return () => clearInterval(id);
  }, []);

  const handleLogout = () => {
    authAPI.logout();
  };

  const userRole = JSON.parse(localStorage.getItem('user') || '{}')?.role;

  // Prefetch the most-used data when user hovers a nav item
  const prefetchRoute = useCallback((route) => {
    const stale = 10 * 60 * 1000;
    if (route === '/leads' || route === '/pipeline' || route === '/lead-analysis') {
      queryClient.prefetchQuery({
        queryKey: ['prefetch', 'leads'],
        queryFn: () => leadsAPI.getAll({ limit: 500 }).then(r => r.data),
        staleTime: stale,
      });
    }
    if (route === '/dashboard' || route === '/followups') {
      queryClient.prefetchQuery({
        queryKey: ['prefetch', 'dashboard-stats'],
        queryFn: () => dashboardAPI.getStats().then(r => r.data),
        staleTime: stale,
      });
    }
    if (route === '/users' || route === '/user-activity' || route === '/lead-analysis' || route === '/lead-update-activity') {
      queryClient.prefetchQuery({
        queryKey: ['prefetch', 'users'],
        queryFn: () => usersAPI.getAll().then(r => r.data),
        staleTime: stale,
      });
    }
    if (route === '/courses') {
      queryClient.prefetchQuery({
        queryKey: ['prefetch', 'courses'],
        queryFn: () => coursesAPI.getAll().then(r => r.data),
        staleTime: stale,
      });
    }
  }, [queryClient]);

  // ── Department-grouped navigation ──────────────────────────────────────────
  // The sidebar used to be one flat ~24-item list filtered by role, which made
  // "which page do I need?" a scavenger hunt. Now it renders the GENERAL pages
  // flat, then one collapsible group per department the user can access
  // (explicit per-user grants from the Team page, falling back to role
  // defaults) — the same config that drives the Departments hub.
  const accessibleDepts = userDepartments(currentUser);

  // Counselors keep their day-to-day pages flat (no groups to dig through).
  const counselorItems = userRole === 'Counselor' ? [
    { key: '/attendance', icon: MapPin, label: 'Attendance' },
    { key: '/followups', icon: CalendarClock, label: "Today's Follow-ups" },
    { key: '/leads', icon: Users, label: 'Leads' },
    { key: '/pipeline', icon: GitBranch, label: 'Pipeline' },
    { key: '/payments', icon: DollarSign, label: 'Payments' },
    { key: '/lead-update-activity', icon: ClipboardList, label: 'Lead Updates' },
  ] : [];

  const generalItems = [...GENERAL_PAGES.slice(0, 3), ...counselorItems, ...GENERAL_PAGES.slice(3)];

  const deptGroups = accessibleDepts.map(key => {
    const dept = DEPARTMENTS[key];
    return {
      ...dept,
      pages: dept.pages.filter(p =>
        userRole === 'Super Admin' || !ADMIN_ONLY_PAGES.includes(p.key)
      ),
    };
  }).filter(g => g.pages.length > 0);

  // Flat list of everything visible — used for the header title lookup and
  // for icon-only rendering when the sidebar is collapsed.
  const allVisibleItems = [
    ...generalItems,
    ...deptGroups.flatMap(g => g.pages),
  ].filter((item, i, arr) => arr.findIndex(x => x.key === item.key) === i);

  // Expand the group containing the current page by default.
  const [expandedDepts, setExpandedDepts] = useState(() => {
    const initial = new Set();
    deptGroups.forEach(g => {
      if (g.pages.some(p => p.key === location.pathname)) initial.add(g.key);
    });
    return initial;
  });

  const toggleDept = (key) => {
    setExpandedDepts(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const navButtonStyle = (isActive) => ({
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: collapsed ? '12px' : '10px 16px',
    marginBottom: 2,
    borderRadius: 8,
    border: 'none',
    background: isActive ? 'var(--bg-tertiary)' : 'transparent',
    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
    cursor: 'pointer',
    fontSize: 'var(--text-sm)',
    fontWeight: isActive ? 500 : 400,
    justifyContent: collapsed ? 'center' : 'flex-start',
  });

  const NavItem = ({ item, indent = false }) => {
    const Icon = item.icon;
    const isActive = location.pathname === item.key;
    return (
      <motion.button
        onClick={() => navigate(item.key)}
        onMouseEnter={() => prefetchRoute(item.key)}
        whileHover={{ x: 2 }}
        whileTap={{ scale: 0.98 }}
        style={{ ...navButtonStyle(isActive), paddingLeft: !collapsed && indent ? 28 : undefined }}
      >
        <Icon size={indent ? 17 : 20} />
        {!collapsed && <span>{item.label}</span>}
      </motion.button>
    );
  };

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg-secondary)' }}>
      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{ width: collapsed ? 64 : 240 }}
        style={{
          background: 'var(--bg-primary)',
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Logo */}
        <div style={{ 
          height: 64, 
          display: 'flex', 
          alignItems: 'center', 
          padding: collapsed ? '0 16px' : '0 24px',
          borderBottom: '1px solid var(--border)',
          gap: 12
        }}>
          <div style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'linear-gradient(135deg, var(--accent), #8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 18,
            flexShrink: 0
          }}>
            🏥
          </div>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ 
                fontSize: 'var(--text-lg)', 
                fontWeight: 600,
                color: 'var(--text-primary)'
              }}
            >
              Med CRM
            </motion.span>
          )}
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '16px 8px', overflowY: 'auto' }}>
          {collapsed ? (
            // Icon-only mode: group headers make no sense, show everything flat
            allVisibleItems.map(item => <NavItem key={item.key} item={item} />)
          ) : (
            <>
              {generalItems.map(item => <NavItem key={item.key} item={item} />)}

              {deptGroups.map(group => {
                const GroupIcon = group.icon;
                const isOpen = expandedDepts.has(group.key);
                const hasActivePage = group.pages.some(p => p.key === location.pathname);
                return (
                  <div key={group.key} style={{ marginTop: 6 }}>
                    <button
                      onClick={() => toggleDept(group.key)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                        padding: '9px 16px', borderRadius: 8, border: 'none',
                        background: 'transparent', cursor: 'pointer',
                        color: hasActivePage ? group.color : 'var(--text-tertiary)',
                        fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                      }}
                    >
                      <GroupIcon size={15} color={group.color} />
                      <span style={{ flex: 1, textAlign: 'left' }}>{group.name}</span>
                      <motion.span animate={{ rotate: isOpen ? 0 : -90 }} transition={{ duration: 0.15 }}
                        style={{ display: 'flex' }}>
                        <ChevronDown size={14} />
                      </motion.span>
                    </button>
                    {isOpen && group.pages.map(page => (
                      <NavItem key={`${group.key}-${page.key}`} item={page} indent />
                    ))}
                  </div>
                );
              })}
            </>
          )}
        </nav>

        {/* Collapse Toggle */}
        <div style={{ padding: 8, borderTop: '1px solid var(--border)' }}>
          <button
            onClick={() => setCollapsed(!collapsed)}
            style={{
              width: '100%',
              padding: 12,
              borderRadius: 8,
              border: 'none',
              background: 'var(--bg-secondary)',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <motion.div
              animate={{ rotate: collapsed ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronLeft size={20} />
            </motion.div>
          </button>
        </div>
      </motion.aside>

      {/* Main Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <header style={{
          height: 64,
          background: 'var(--bg-primary)',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
        }}>
          <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 600, color: 'var(--text-primary)' }}>
            {allVisibleItems.find(item => item.key === location.pathname)?.label || 'Dashboard'}
          </h1>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Search */}
            <SearchBar />

            {/* Smart Notifications */}
            {isFeatureEnabled('SMART_NOTIFICATIONS') && <SmartNotifications />}

            {/* User + Logout */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              paddingLeft: 16,
              borderLeft: '1px solid var(--border)',
            }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>
                  {currentUser.full_name || 'User'}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                  {currentUser.role || ''}
                </div>
              </div>
              <div style={{
                width: 40,
                height: 40,
                borderRadius: 8,
                background: 'linear-gradient(135deg, var(--accent), #8b5cf6)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
                fontWeight: 600,
                fontSize: 'var(--text-sm)',
              }}>
                {initials}
              </div>
              <button
                onClick={handleLogout}
                title="Logout"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  padding: 8,
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                }}
              >
                <LogOut size={18} />
              </button>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main style={{ 
          flex: 1, 
          overflow: 'auto', 
          padding: 24,
        }}>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            {children}
          </motion.div>
        </main>
      </div>
    </div>
  );
};

export default ProfessionalLayout;
