import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { setCsrfTokenGlobal, getCsrfToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/auth/me', {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data);
        setCsrfTokenGlobal(data.csrf_token);
      } else {
        setUser(null);
        setCsrfTokenGlobal(null);
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = useCallback((provider = 'entra') => {
    window.location.href = `/api/v1/auth/login?provider=${provider}`;
  }, []);

  const logout = useCallback(async () => {
    try {
      const csrf = getCsrfToken();
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-Token': csrf } : {},
      });
    } catch (err) {
      console.error('Logout failed:', err);
    }
    setCsrfTokenGlobal(null);
    setUser(null);
    window.location.href = '/';
  }, []);

  const isAuthenticated = user !== null;

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, isLoading, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
