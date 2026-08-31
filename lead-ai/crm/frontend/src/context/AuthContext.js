/**
 * AuthContext — single source of truth for the authenticated user.
 *
 * Replaces scattered `localStorage.getItem('user')` calls throughout the
 * codebase.  Any component can use `useAuth()` to get the current user and
 * the `logout` helper.
 *
 * Token expiry is detected by the axios 401 interceptor in api.js which
 * calls `logout()` from this context.
 */

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import api from '../api/api';
import { setServerPermissions } from '../config/rbac';

const AuthContext = createContext(null);

const STORAGE_KEY = 'user';

function loadStoredUser() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => loadStoredUser());

  // Sync across browser tabs (e.g., logout in one tab → logout everywhere)
  useEffect(() => {
    function onStorage(e) {
      if (e.key === STORAGE_KEY) {
        setUser(e.newValue ? JSON.parse(e.newValue) : null);
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  // Pull the CURRENT server-side identity + effective permissions. This is
  // what the UI should trust: a role change on the server takes effect here
  // on the next load / navigation instead of waiting for the token to expire.
  const refreshIdentity = useCallback(async () => {
    try {
      const { data } = await api.get('/api/auth/me');
      if (!data) return;
      setServerPermissions(data.permissions || []);
      setUser((prev) => {
        if (!prev) return prev;
        // keep the token, adopt the server's live role / flags
        const merged = {
          ...prev,
          role: data.role,
          is_active: data.is_active,
          permissions: data.permissions || [],
          departments: data.departments || prev.departments,
          page_grants: data.page_grants || prev.page_grants,
        };
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(merged)); } catch { /* ignore */ }
        return merged;
      });
    } catch {
      // 401 is handled by the api interceptor (redirect to login).
      // Other errors: leave the last-known identity in place.
    }
  }, []);

  useEffect(() => {
    if (user?.token) refreshIdentity();
  }, [user?.token, refreshIdentity]);

  const login = useCallback((userData) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(userData));
    setUser(userData);
    if (Array.isArray(userData?.permissions)) setServerPermissions(userData.permissions);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setServerPermissions(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, refreshIdentity, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Hook to access the auth context.
 * Throws if used outside of <AuthProvider>.
 */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
}
