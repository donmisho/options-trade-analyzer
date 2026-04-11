import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { setCsrfTokenGlobal } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState(null);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/auth/me', {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data);
        setIsAuthenticated(true);
        setCsrfToken(data.csrf_token);
        setCsrfTokenGlobal(data.csrf_token);
      } else {
        setUser(null);
        setIsAuthenticated(false);
        setCsrfToken(null);
        setCsrfTokenGlobal(null);
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      setUser(null);
      setIsAuthenticated(false);
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
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
      });
    } catch (err) {
      console.error('Logout failed:', err);
    }
    setUser(null);
    setIsAuthenticated(false);
    setCsrfToken(null);
    setCsrfTokenGlobal(null);
    window.location.href = '/';
  }, [csrfToken]);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, isLoading, csrfToken, login, logout, checkAuth }}>
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
