/**
 * Toast Notification System
 * Global notification manager for success, error, warning, and info messages
 */

import { create } from 'zustand';

export const useToastStore = create((set, get) => ({
  toasts: [],
  
  addToast: ({ message, type = 'info', duration = 4000, action = null }) => {
    const id = Date.now() + Math.random();
    const toast = { id, message, type, action, createdAt: Date.now() };
    
    set((state) => ({
      toasts: [...state.toasts, toast],
    }));
    
    if (duration > 0) {
      setTimeout(() => {
        get().removeToast(id);
      }, duration);
    }
    
    return id;
  },
  
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },
  
  clearAll: () => {
    set({ toasts: [] });
  },
}));

// Convenience methods
export const toast = {
  success: (message, options = {}) => 
    useToastStore.getState().addToast({ message, type: 'success', ...options }),
  
  error: (message, options = {}) => 
    useToastStore.getState().addToast({ message, type: 'error', duration: 6000, ...options }),
  
  warning: (message, options = {}) => 
    useToastStore.getState().addToast({ message, type: 'warning', ...options }),
  
  info: (message, options = {}) => 
    useToastStore.getState().addToast({ message, type: 'info', ...options }),
  
  loading: (message, options = {}) => 
    useToastStore.getState().addToast({ message, type: 'loading', duration: 0, ...options }),
};

export default toast;
