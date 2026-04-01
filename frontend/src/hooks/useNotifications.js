/**
 * useNotifications - React hook for real-time notification management
 * Integrates with WebSocket backend for real-time updates
 * Supports notification preferences, alert rules, and delivery channels
 * Jakarta timezone (WIB: UTC+7) aware with BEI trading hours
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

export const useNotifications = (userId) => {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [preferences, setPreferences] = useState(null);
  const [alertRules, setAlertRules] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState(null);
  
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;
  const baseReconnectDelay = 1000; // 1 second

  /**
   * Connect to WebSocket for real-time notifications
   */
  const connectWebSocket = useCallback(() => {
    if (!userId) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/notifications/ws/${userId}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('[Notifications] WebSocket connected');
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        
        // Send initial ping
        ws.send(JSON.stringify({ type: 'ping' }));
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          switch (message.type) {
            case 'notification':
              // New notification received
              setNotifications((prev) => [message.data, ...prev]);
              setUnreadCount((prev) => prev + 1);
              
              // Trigger notification sound/browser notification
              if ('Notification' in window && Notification.permission === 'granted') {
                new Notification(message.data.title, {
                  body: message.data.body,
                  icon: '/logo.png',
                  badge: '/badge.png',
                });
              }
              break;

            case 'pong':
              // Response to ping (keep-alive)
              console.log('[Notifications] Pong received');
              break;

            case 'unread_count':
              // Update unread count
              setUnreadCount(message.count);
              break;

            case 'notification_read':
              // Mark notification as read
              setNotifications((prev) =>
                prev.map((notif) =>
                  notif.id === message.notification_id
                    ? { ...notif, read: true, read_at: new Date().toISOString() }
                    : notif
                )
              );
              setUnreadCount((prev) => Math.max(0, prev - 1));
              break;

            default:
              console.warn('[Notifications] Unknown message type:', message.type);
          }
        } catch (err) {
          console.error('[Notifications] Error parsing message:', err);
        }
      };

      ws.onerror = (event) => {
        console.error('[Notifications] WebSocket error:', event);
        setError('WebSocket connection error');
      };

      ws.onclose = () => {
        console.log('[Notifications] WebSocket closed');
        setIsConnected(false);

        // Attempt to reconnect with exponential backoff
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = baseReconnectDelay * Math.pow(2, reconnectAttemptsRef.current);
          console.log(`[Notifications] Attempting to reconnect in ${delay}ms...`);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current += 1;
            connectWebSocket();
          }, delay);
        } else {
          setError('Max reconnection attempts reached');
        }
      };

      wsRef.current = ws;
    } catch (err) {
      console.error('[Notifications] WebSocket connection failed:', err);
      setError('Failed to establish WebSocket connection');
    }
  }, [userId]);

  /**
   * Fetch notifications history from API
   */
  const fetchNotifications = useCallback(async (limit = 50, offset = 0) => {
    if (!userId) return;

    try {
      setIsLoading(true);
      setError(null);

      const response = await fetch(
        `${API_BASE_URL}/notifications/history/${userId}?limit=${limit}&offset=${offset}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to fetch notifications');

      const data = await response.json();
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch (err) {
      console.error('[Notifications] Fetch error:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  /**
   * Fetch unread count
   */
  const fetchUnreadCount = useCallback(async () => {
    if (!userId) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/unread/${userId}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to fetch unread count');

      const data = await response.json();
      setUnreadCount(data.unread_count || 0);
    } catch (err) {
      console.error('[Notifications] Unread count error:', err);
    }
  }, [userId]);

  /**
   * Mark a notification as read
   */
  const markAsRead = useCallback(async (notificationId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/mark-read/${notificationId}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to mark notification as read');

      // Update local state
      setNotifications((prev) =>
        prev.map((notif) =>
          notif.id === notificationId
            ? { ...notif, read: true, read_at: new Date().toISOString() }
            : notif
        )
      );

      // Notify WebSocket (if available)
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'mark_read',
            notification_id: notificationId,
          })
        );
      }

      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch (err) {
      console.error('[Notifications] Mark read error:', err);
      setError(err.message);
    }
  }, []);

  /**
   * Mark all notifications as read
   */
  const markAllAsRead = useCallback(async () => {
    // Send mark_read for all unread notifications
    const unreadNotifications = notifications.filter((n) => !n.read);
    
    for (const notif of unreadNotifications) {
      await markAsRead(notif.id);
    }
  }, [notifications, markAsRead]);

  /**
   * Fetch user preferences
   */
  const fetchPreferences = useCallback(async () => {
    if (!userId) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/preferences/${userId}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
        }
      );

      if (!response.ok && response.status !== 404) {
        throw new Error('Failed to fetch preferences');
      }

      const data = await response.json();
      setPreferences(data);
    } catch (err) {
      console.error('[Notifications] Preferences error:', err);
      // Don't set error state for missing preferences
    }
  }, [userId]);

  /**
   * Update user preferences
   */
  const updatePreferences = useCallback(async (updates) => {
    if (!userId) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/preferences/${userId}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
          body: JSON.stringify(updates),
        }
      );

      if (!response.ok) throw new Error('Failed to update preferences');

      const data = await response.json();
      setPreferences(data);
      return data;
    } catch (err) {
      console.error('[Notifications] Update preferences error:', err);
      setError(err.message);
      throw err;
    }
  }, [userId]);

  /**
   * Fetch alert rules
   */
  const fetchAlertRules = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/rules`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to fetch alert rules');

      const data = await response.json();
      setAlertRules(data.rules || []);
    } catch (err) {
      console.error('[Notifications] Alert rules error:', err);
      setError(err.message);
    }
  }, []);

  /**
   * Create alert rule
   */
  const createAlertRule = useCallback(async (rule) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/rules`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
          body: JSON.stringify(rule),
        }
      );

      if (!response.ok) throw new Error('Failed to create alert rule');

      const data = await response.json();
      setAlertRules((prev) => [...prev, data.rule]);
      return data.rule;
    } catch (err) {
      console.error('[Notifications] Create rule error:', err);
      setError(err.message);
      throw err;
    }
  }, []);

  /**
   * Update alert rule
   */
  const updateAlertRule = useCallback(async (ruleId, updates) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/rules/${ruleId}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
          body: JSON.stringify(updates),
        }
      );

      if (!response.ok) throw new Error('Failed to update alert rule');

      const data = await response.json();
      setAlertRules((prev) =>
        prev.map((rule) => (rule.id === ruleId ? data.rule : rule))
      );
      return data.rule;
    } catch (err) {
      console.error('[Notifications] Update rule error:', err);
      setError(err.message);
      throw err;
    }
  }, []);

  /**
   * Delete alert rule
   */
  const deleteAlertRule = useCallback(async (ruleId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/rules/${ruleId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to delete alert rule');

      setAlertRules((prev) => prev.filter((rule) => rule.id !== ruleId));
    } catch (err) {
      console.error('[Notifications] Delete rule error:', err);
      setError(err.message);
      throw err;
    }
  }, []);

  /**
   * Fetch system stats
   */
  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/notifications/stats`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`,
          },
        }
      );

      if (!response.ok) throw new Error('Failed to fetch stats');

      const data = await response.json();
      setStats(data);
    } catch (err) {
      console.error('[Notifications] Stats error:', err);
    }
  }, []);

  /**
   * Disconnect WebSocket
   */
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    setIsConnected(false);
  }, []);

  /**
   * Request browser notification permission
   */
  const requestNotificationPermission = useCallback(async () => {
    if ('Notification' in window && Notification.permission === 'default') {
      const permission = await Notification.requestPermission();
      return permission === 'granted';
    }
    return false;
  }, []);

  /**
   * Initialize hook on mount and userId change
   */
  useEffect(() => {
    if (!userId) return;

    // Fetch initial data
    fetchNotifications();
    fetchUnreadCount();
    fetchPreferences();
    fetchAlertRules();
    fetchStats();

    // Request browser notification permission
    requestNotificationPermission();

    // Connect WebSocket
    connectWebSocket();

    // Set up polling for unread count (every 30 seconds)
    const unreadCountInterval = setInterval(fetchUnreadCount, 30000);

    // Clean up on unmount or userId change
    return () => {
      clearInterval(unreadCountInterval);
      disconnect();
    };
  }, [userId]);

  return {
    // State
    notifications,
    unreadCount,
    isConnected,
    preferences,
    alertRules,
    isLoading,
    error,
    stats,

    // Notification methods
    fetchNotifications,
    markAsRead,
    markAllAsRead,

    // Preference methods
    fetchPreferences,
    updatePreferences,

    // Alert rule methods
    fetchAlertRules,
    createAlertRule,
    updateAlertRule,
    deleteAlertRule,

    // Utility methods
    fetchStats,
    requestNotificationPermission,
    disconnect,
    reconnect: connectWebSocket,
  };
};

export default useNotifications;
