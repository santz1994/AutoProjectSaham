/**
 * useAccessibility Hook
 * WCAG 2.1 AAA compliance hook for React components
 * Manages focus, keyboard navigation, ARIA state, and accessibility preferences
 * 
 * @module frontend/src/hooks/useAccessibility
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import a11y from '../utils/a11y';

/**
 * Main accessibility hook
 * Provides comprehensive a11y helpers and state management
 * 
 * @param {object} options
 * @param {string} options.role - ARIA role
 * @param {string} options.ariaLabel - Accessible name
 * @param {string} options.ariaLabelledBy - ID of label element
 * @param {string} options.ariaDescribedBy - ID of description element
 * @param {boolean} options.trapFocus - Trap focus in container (modals)
 * @param {boolean} options.autoFocusFirst - Auto-focus first element
 * @param {function} options.onEscape - Callback when Escape is pressed
 * 
 * @returns {object} Accessibility helpers and state
 */
export const useAccessibility = (options = {}) => {
  const {
    role,
    ariaLabel,
    ariaLabelledBy,
    ariaDescribedBy,
    trapFocus: shouldTrapFocus = false,
    autoFocusFirst = false,
    onEscape,
  } = options;

  const containerRef = useRef(null);
  const [focusableElements, setFocusableElements] = useState([]);
  const [ariaId] = useState(() => a11y.generateAriaId('a11y'));
  const focusTrapCleanup = useRef(null);

  // Get focusable elements in container
  useEffect(() => {
    if (containerRef.current) {
      const elements = a11y.getFocusableElements(containerRef.current);
      setFocusableElements(elements);

      if (autoFocusFirst && elements.length > 0) {
        elements[0].focus();
      }
    }
  }, [autoFocusFirst]);

  // Set up focus trap if needed
  useEffect(() => {
    if (shouldTrapFocus && containerRef.current) {
      focusTrapCleanup.current = a11y.trapFocus(containerRef.current);

      return () => {
        if (focusTrapCleanup.current) {
          focusTrapCleanup.current();
        }
      };
    }
  }, [shouldTrapFocus]);

  // Handle keyboard events
  const handleKeyDown = useCallback(
    (event) => {
      // Escape key
      if (event.key === 'Escape' && onEscape) {
        event.preventDefault();
        onEscape();
      }
    },
    [onEscape]
  );

  // Attach keyboard handler
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.addEventListener('keydown', handleKeyDown);

      return () => {
        containerRef.current?.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [handleKeyDown]);

  // Set ARIA attributes on container
  useEffect(() => {
    if (containerRef.current) {
      if (role) containerRef.current.setAttribute('role', role);
      if (ariaLabel) containerRef.current.setAttribute('aria-label', ariaLabel);
      if (ariaLabelledBy) {
        containerRef.current.setAttribute('aria-labelledby', ariaLabelledBy);
      }
      if (ariaDescribedBy) {
        containerRef.current.setAttribute('aria-describedby', ariaDescribedBy);
      }
    }
  }, [role, ariaLabel, ariaLabelledBy, ariaDescribedBy]);

  return {
    // Refs
    containerRef,
    ariaId,

    // State
    focusableElements,

    // Methods
    focusFirst: () => {
      if (focusableElements.length > 0) {
        focusableElements[0].focus();
      }
    },

    focusLast: () => {
      if (focusableElements.length > 0) {
        focusableElements[focusableElements.length - 1].focus();
      }
    },

    focusIndex: (index) => {
      if (focusableElements[index]) {
        focusableElements[index].focus();
      }
    },

    focusElement: (selector) => a11y.focusFirstElement(selector, containerRef.current),

    // Utilities
    announce: (message, priority = 'polite') => {
      a11y.announceToScreenReader(message, priority);
    },

    setAriaLabel: (label) => {
      if (containerRef.current) {
        a11y.setAriaLabel(containerRef.current, label);
      }
    },

    setAriaDescribedBy: (descriptionId) => {
      if (containerRef.current) {
        a11y.setAriaDescribedBy(containerRef.current, descriptionId);
      }
    },

    setAriaLabeledBy: (labelId) => {
      if (containerRef.current) {
        a11y.setAriaLabeledBy(containerRef.current, labelId);
      }
    },
  };
};

/**
 * Hook for keyboard navigation
 * Handles arrow keys for menu/list navigation
 * 
 * @param {object} options
 * @param {string} options.direction - 'vertical' or 'horizontal'
 * @param {boolean} options.looping - Wrap around at edges
 * @param {function} options.onSelect - Called when Enter/Space pressed
 * 
 * @returns {object} Keyboard state and handlers
 */
export const useKeyboardNavigation = (options = {}) => {
  const {
    direction = 'vertical',
    looping = true,
    onSelect,
  } = options;

  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = useRef(null);

  const isVertical = direction === 'vertical';
  const navigationKeys = isVertical
    ? ['ArrowUp', 'ArrowDown']
    : ['ArrowLeft', 'ArrowRight'];
  const previousKey = isVertical ? 'ArrowUp' : 'ArrowLeft';

  const handleKeyDown = useCallback(
    (event) => {
      const { key } = event;

      if (navigationKeys.includes(key)) {
        event.preventDefault();

        setSelectedIndex((prev) => {
          let next = prev;

          if (key === previousKey) {
            next = looping ? (prev === 0 ? Infinity : prev - 1) : Math.max(0, prev - 1);
          } else {
            const maxIndex = containerRef.current
              ? a11y.getFocusableElements(containerRef.current).length - 1
              : 0;
            next = looping ? (prev + 1) % (maxIndex + 1) : Math.min(maxIndex, prev + 1);
          }

          return next;
        });
      } else if (a11y.isActivationKey(event)) {
        event.preventDefault();
        if (onSelect) {
          onSelect(selectedIndex);
        }
      } else if (key === 'Home') {
        event.preventDefault();
        setSelectedIndex(0);
      } else if (key === 'End') {
        event.preventDefault();
        const maxIndex = containerRef.current
          ? a11y.getFocusableElements(containerRef.current).length - 1
          : 0;
        setSelectedIndex(maxIndex);
      }
    },
    [navigationKeys, previousKey, looping, onSelect]
  );

  return {
    containerRef,
    selectedIndex,
    setSelectedIndex,
    handleKeyDown,
  };
};

/**
 * Hook for managing focus in modals and overlays
 * Saves focus before opening, restores after closing
 * 
 * @param {boolean} isOpen - Modal/overlay open state
 * @returns {object} {saveFocus, restoreFocus}
 */
export const useFocusRestore = (isOpen) => {
  const { saveFocus, restoreFocus } = a11y.useFocusRestore();

  useEffect(() => {
    if (isOpen) {
      saveFocus();
    } else {
      restoreFocus();
    }
  }, [isOpen, saveFocus, restoreFocus]);

  return { saveFocus, restoreFocus };
};

/**
 * Hook for ARIA live regions
 * Announces dynamic content changes to screen readers
 * 
 * @param {object} options
 * @param {string} options.priority - 'polite' or 'assertive'
 * @param {boolean} options.atomic - Announce entire content
 * 
 * @returns {object} {announce, liveRegionProps, clear}
 */
export const useAriaLive = (options = {}) => {
  const { priority = 'polite', atomic = true } = options;

  const [announcement, setAnnouncement] = useState('');
  const liveRegionId = useState(() => a11y.generateAriaId('aria-live'))[0];

  const announce = useCallback(
    (message, duration = 3000) => {
      setAnnouncement(message);

      if (duration > 0) {
        setTimeout(() => setAnnouncement(''), duration);
      }
    },
    []
  );

  const clear = useCallback(() => {
    setAnnouncement('');
  }, []);

  return {
    announce,
    clear,
    liveRegionProps: {
      id: liveRegionId,
      role: 'status',
      'aria-live': priority,
      'aria-atomic': atomic,
      className: 'sr-only', // Visually hidden
    },
    announcement,
  };
};

/**
 * Hook for managing reduced motion preference
 * Returns current preference and safe animation duration
 * 
 * @returns {object} {prefersReducedMotion, safeAnimationDuration}
 */
export const useReducedMotion = () => {
  const [prefersReduced, setPrefersReduced] = useState(() =>
    a11y.prefersReducedMotion()
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

    const handleChange = (e) => {
      setPrefersReduced(e.matches);
    };

    mediaQuery.addEventListener('change', handleChange);

    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  return {
    prefersReducedMotion: prefersReduced,
    safeAnimationDuration: (normalDuration = 300, reducedDuration = 0) =>
      a11y.getAnimationDuration(normalDuration, reducedDuration),
  };
};

/**
 * Hook for Jakarta timezone-aware time announcements
 * Helps screen reader users understand time context
 * 
 * @param {Date} date
 * @returns {object} {announcement, formatted}
 */
export const useJakartaTime = (date) => {
  const announcement = a11y.getLocalizedTimeAnnouncement(date);
  const formatted = date.toLocaleString('id-ID', {
    timeZone: 'Asia/Jakarta',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

  return { announcement, formatted };
};

/**
 * Hook for localized currency announcements
 * Helps screen reader users understand amounts in IDR
 * 
 * @param {number} amount - Amount in IDR
 * @returns {object} {announcement, formatted}
 */
export const useLocalizedCurrency = (amount) => {
  const announcement = a11y.getLocalizedCurrencyAnnouncement(amount);
  const formatted = new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
  }).format(amount);

  return { announcement, formatted };
};

/**
 * Hook for accessibility audit
 * Runs comprehensive audit on component mount/when dependencies change
 * Useful for development/testing
 * 
 * @param {HTMLElement} container - Container to audit
 * @param {any[]} dependencies - Re-run audit when dependencies change
 * @returns {object} Audit results
 */
export const useA11yAudit = (container, dependencies = []) => {
  const [auditResults, setAuditResults] = useState(null);

  useEffect(() => {
    if (container && import.meta.env.DEV) {
      const results = a11y.runA11yAudit(container);
      setAuditResults(results);

      // Log issues to console
      if (results.headingHierarchy.issues.length > 0) {
        console.warn('A11y: Heading hierarchy issues:', results.headingHierarchy.issues);
      }
      if (results.formLabels.issues.length > 0) {
        console.warn('A11y: Form label issues:', results.formLabels.issues);
      }
    }
  }, [container, ...dependencies]);

  return auditResults;
};

export default {
  useAccessibility,
  useKeyboardNavigation,
  useFocusRestore,
  useAriaLive,
  useReducedMotion,
  useJakartaTime,
  useLocalizedCurrency,
  useA11yAudit,
};
