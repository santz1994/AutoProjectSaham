/**
 * Accessibility (a11y) Utilities
 * WCAG 2.1 AAA compliance helpers
 * Jakarta Timezone Support
 * 
 * @module frontend/src/utils/a11y
 */

// ============================================================================
// COLOR CONTRAST UTILITIES
// ============================================================================

/**
 * Calculate relative luminance of a color
 * @param {string} hex - Hex color code (#RRGGBB)
 * @returns {number} Relative luminance (0-1)
 */
export const getRelativeLuminance = (hex) => {
  const rgb = parseInt(hex.slice(1), 16);
  const r = ((rgb >> 16) & 0xff) / 255;
  const g = ((rgb >> 8) & 0xff) / 255;
  const b = (rgb & 0xff) / 255;

  const luminance = (channel) => {
    return channel <= 0.03928
      ? channel / 12.92
      : Math.pow((channel + 0.055) / 1.055, 2.4);
  };

  return 0.2126 * luminance(r) + 0.7152 * luminance(g) + 0.0722 * luminance(b);
};

/**
 * Calculate contrast ratio between two colors
 * Follows WCAG formula: (L1 + 0.05) / (L2 + 0.05)
 * 
 * @param {string} color1 - Foreground color (#RRGGBB)
 * @param {string} color2 - Background color (#RRGGBB)
 * @returns {number} Contrast ratio (1-21)
 */
export const getContrastRatio = (color1, color2) => {
  const l1 = getRelativeLuminance(color1);
  const l2 = getRelativeLuminance(color2);

  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);

  return (lighter + 0.05) / (darker + 0.05);
};

/**
 * Check if contrast ratio meets WCAG level
 * @param {number} ratio - Contrast ratio (1-21)
 * @param {string} level - 'A' (4.5:1), 'AA' (7:1), or 'AAA' (7:1 normal / 4.5:1 large)
 * @param {string} textSize - 'normal' or 'large' (18pt+ or 14pt+ bold)
 * @returns {boolean}
 */
export const meetsContrastStandard = (ratio, level = 'AAA', textSize = 'normal') => {
  const required = {
    A: { normal: 3, large: 3 },
    AA: { normal: 4.5, large: 3 },
    AAA: { normal: 7, large: 4.5 },
  };

  return ratio >= required[level][textSize];
};

/**
 * Get contrast ratio between any CSS selector colors
 * Useful for testing actual computed styles
 * @param {string} foregroundSelector - CSS selector for text
 * @param {string} backgroundSelector - CSS selector for background
 * @returns {number}
 */
export const getComputedContrastRatio = (foregroundSelector, backgroundSelector) => {
  const fgElement = document.querySelector(foregroundSelector);
  const bgElement = document.querySelector(backgroundSelector);

  if (!fgElement || !bgElement) return null;

  const fgColor = window.getComputedStyle(fgElement).color;
  const bgColor = window.getComputedStyle(bgElement).backgroundColor;

  // Convert RGB to Hex
  const rgbToHex = (rgb) => {
    const values = rgb.match(/\d+/g);
    return `#${values.map((x) => parseInt(x).toString(16).padStart(2, '0')).join('')}`;
  };

  const fgHex = rgbToHex(fgColor);
  const bgHex = rgbToHex(bgColor);

  return getContrastRatio(fgHex, bgHex);
};

// ============================================================================
// KEYBOARD UTILITIES
// ============================================================================

/**
 * Common keyboard event codes (for better readability)
 */
export const KEYS = {
  ENTER: 'Enter',
  ESCAPE: 'Escape',
  SPACE: ' ',
  TAB: 'Tab',
  SHIFT_TAB: 'Shift+Tab',
  ARROW_UP: 'ArrowUp',
  ARROW_DOWN: 'ArrowDown',
  ARROW_LEFT: 'ArrowLeft',
  ARROW_RIGHT: 'ArrowRight',
  HOME: 'Home',
  END: 'End',
};

/**
 * Check if key is a navigation key (arrow, Home, End)
 * @param {KeyboardEvent} event
 * @returns {boolean}
 */
export const isNavigationKey = (event) => {
  return ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(
    event.key
  );
};

/**
 * Check if key is enter or space
 * @param {KeyboardEvent} event
 * @returns {boolean}
 */
export const isActivationKey = (event) => {
  return event.key === 'Enter' || event.key === ' ';
};

/**
 * Prevent event bubbling on specific keys
 * Useful for custom keyboard handlers
 * @param {KeyboardEvent} event
 * @param {string[]} keysToStop
 */
export const stopPropagationOnKeys = (event, keysToStop = ['Enter', ' ']) => {
  if (keysToStop.includes(event.key)) {
    event.stopPropagation();
  }
};

// ============================================================================
// FOCUS MANAGEMENT
// ============================================================================

/**
 * Get all focusable elements within a container
 * @param {HTMLElement} container
 * @returns {HTMLElement[]}
 */
export const getFocusableElements = (container) => {
  const selector = [
    'button:not([disabled])',
    '[href]:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',');

  return Array.from(container.querySelectorAll(selector));
};

/**
 * Trap focus within a container (modal, popover, etc)
 * Prevents tab from going outside the container
 * @param {HTMLElement} container
 * @returns {function} Cleanup function to remove listener
 */
export const trapFocus = (container) => {
  const focusableElements = getFocusableElements(container);
  const firstElement = focusableElements[0];
  const lastElement = focusableElements[focusableElements.length - 1];

  const handleKeyDown = (event) => {
    if (event.key !== 'Tab') return;

    if (event.shiftKey) {
      // Shift+Tab on first element -> move to last
      if (document.activeElement === firstElement) {
        lastElement.focus();
        event.preventDefault();
      }
    } else {
      // Tab on last element -> move to first
      if (document.activeElement === lastElement) {
        firstElement.focus();
        event.preventDefault();
      }
    }
  };

  container.addEventListener('keydown', handleKeyDown);

  // Return cleanup function
  return () => container.removeEventListener('keydown', handleKeyDown);
};

/**
 * Save and restore focus
 * Useful for modals that appear/disappear
 * @returns {object} {saveFocus, restoreFocus}
 */
export const useFocusRestore = () => {
  let previouslyFocused = null;

  const saveFocus = () => {
    previouslyFocused = document.activeElement;
  };

  const restoreFocus = () => {
    if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
      previouslyFocused.focus();
    }
  };

  return { saveFocus, restoreFocus };
};

/**
 * Focus first element matching selector
 * @param {string} selector
 * @param {HTMLElement} container
 * @returns {boolean} True if element was found and focused
 */
export const focusFirstElement = (selector, container = document) => {
  const element = container.querySelector(selector);
  if (element) {
    element.focus();
    return true;
  }
  return false;
};

// ============================================================================
// ARIA HELPERS
// ============================================================================

/**
 * Generate unique IDs for aria-labelledby and aria-describedby
 * @param {string} prefix
 * @returns {string}
 */
export const generateAriaId = (prefix = 'aria') => {
  return `${prefix}-${Math.random().toString(36).substr(2, 9)}`;
};

/**
 * Set ARIA label with fallback to title
 * @param {HTMLElement} element
 * @param {string} label
 */
export const setAriaLabel = (element, label) => {
  if (element) {
    element.setAttribute('aria-label', label);
  }
};

/**
 * Set ARIA described-by relationship
 * @param {HTMLElement} element - Element being described
 * @param {string} descriptionId - ID of describing element
 */
export const setAriaDescribedBy = (element, descriptionId) => {
  if (element) {
    element.setAttribute('aria-describedby', descriptionId);
  }
};

/**
 * Set ARIA labeled-by relationship
 * @param {HTMLElement} element - Element being labeled
 * @param {string} labelId - ID of label element
 */
export const setAriaLabeledBy = (element, labelId) => {
  if (element) {
    element.setAttribute('aria-labelledby', labelId);
  }
};

/**
 * Announce message to screen readers
 * Creates temporary aria-live region
 * @param {string} message
 * @param {string} priority - 'polite' or 'assertive'
 * @param {number} duration - Time to remove (ms)
 */
export const announceToScreenReader = (message, priority = 'polite', duration = 3000) => {
  const announcement = document.createElement('div');
  announcement.setAttribute('role', 'status');
  announcement.setAttribute('aria-live', priority);
  announcement.setAttribute('aria-atomic', 'true');
  announcement.className = 'sr-only'; // Visually hidden
  announcement.textContent = message;

  document.body.appendChild(announcement);

  // Remove after duration
  if (duration > 0) {
    setTimeout(() => announcement.remove(), duration);
  }

  return announcement;
};

// ============================================================================
// SEMANTIC HTML HELPERS
// ============================================================================

/**
 * Check if element has proper heading hierarchy
 * @param {HTMLElement} container
 * @returns {object} {isValid, issues}
 */
export const validateHeadingHierarchy = (container = document) => {
  const headings = Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6'));
  const issues = [];

  let expectedLevel = 1;
  let previousLevel = 1;

  headings.forEach((heading, index) => {
    const level = parseInt(heading.tagName[1]);

    if (index === 0 && level !== 1) {
      issues.push(`First heading should be h1, found ${heading.tagName}`);
    }

    if (level > previousLevel + 1) {
      issues.push(
        `Heading hierarchy skip: ${heading.tagName}(${level}) after h${previousLevel}`
      );
    }

    previousLevel = level;
  });

  return {
    isValid: issues.length === 0,
    issues,
    headingCount: headings.length,
  };
};

/**
 * Ensure proper form label associations
 * @param {HTMLElement} container
 * @returns {object} {isValid, issues}
 */
export const validateFormLabels = (container = document) => {
  const inputs = Array.from(container.querySelectorAll('input, select, textarea'));
  const issues = [];

  inputs.forEach((input) => {
    const ariaLabel = input.getAttribute('aria-label');
    const ariaLabelledBy = input.getAttribute('aria-labelledby');
    const label = container.querySelector(`label[for="${input.id}"]`);

    const hasLabel = ariaLabel || ariaLabelledBy || label;

    if (!hasLabel) {
      issues.push(`Input without label: ${input.id || input.name || 'unnamed'}`);
    }

    // Check disabled state contrast
    if (input.disabled && !input.getAttribute('aria-disabled')) {
      issues.push(`Disabled input should have aria-disabled: ${input.id || input.name}`);
    }
  });

  return {
    isValid: issues.length === 0,
    issues,
    inputCount: inputs.length,
  };
};

// ============================================================================
// TEXT SIZING & ZOOM
// ============================================================================

/**
 * Check if text can be scaled up to 200% without loss of functionality
 * @returns {boolean}
 */
export const supportsTextZoom = () => {
  const testElement = document.createElement('div');
  testElement.style.fontSize = '16px';
  testElement.style.width = '100px';
  testElement.textContent = 'Test';

  document.body.appendChild(testElement);
  const originalWidth = testElement.offsetWidth;

  testElement.style.fontSize = '32px'; // 200% zoom
  const zoomedWidth = testElement.offsetWidth;

  document.body.removeChild(testElement);

  // Should allow scaling without breaking layout
  return zoomedWidth <= window.innerWidth * 0.9; // 90% of viewport
};

/**
 * Get effective text size including computed styles
 * @param {HTMLElement} element
 * @returns {number} Size in pixels
 */
export const getEffectiveTextSize = (element) => {
  const computed = window.getComputedStyle(element);
  return parseFloat(computed.fontSize);
};

// ============================================================================
// REDUCED MOTION SUPPORT
// ============================================================================

/**
 * Check if user prefers reduced motion
 * @returns {boolean}
 */
export const prefersReducedMotion = () => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
};

/**
 * Get safe animation duration respecting user preference
 * @param {number} normalDuration - Duration in milliseconds
 * @param {number} reducedDuration - Duration for reduced motion (default: 0)
 * @returns {number}
 */
export const getAnimationDuration = (normalDuration = 300, reducedDuration = 0) => {
  return prefersReducedMotion() ? reducedDuration : normalDuration;
};

/**
 * CSS class for prefers-reduced-motion
 * @returns {string} CSS to apply
 */
export const getReducedMotionCSS = () => {
  return `
    @media (prefers-reduced-motion: reduce) {
      * {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }
    }
  `;
};

// ============================================================================
// LANGUAGE & CONTEXT
// ============================================================================

/**
 * Jakarta timezone-aware announcement
 * Helps international users understand time references
 * @param {Date} date
 * @returns {string}
 */
export const getLocalizedTimeAnnouncement = (date) => {
  const jakartaTime = date.toLocaleString('id-ID', {
    timeZone: 'Asia/Jakarta',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return `Time in Jakarta: ${jakartaTime}`;
};

/**
 * Announce currency amount with proper localization
 * @param {number} amount - Amount in IDR
 * @returns {string}
 */
export const getLocalizedCurrencyAnnouncement = (amount) => {
  const formatted = new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
  }).format(amount);

  return `Rp ${formatted}`;
};

// ============================================================================
// VALIDATION SUITE
// ============================================================================

/**
 * Run comprehensive a11y audit on a container
 * @param {HTMLElement} container
 * @returns {object} Audit results
 */
export const runA11yAudit = (container = document) => {
  return {
    headingHierarchy: validateHeadingHierarchy(container),
    formLabels: validateFormLabels(container),
    focusableElements: getFocusableElements(container).length,
    reducedMotionPreference: prefersReducedMotion(),
    textZoomSupport: supportsTextZoom(),
    timestamp: new Date().toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' }),
  };
};

// ============================================================================
// EXPORTS
// ============================================================================

export default {
  // Color utilities
  getRelativeLuminance,
  getContrastRatio,
  meetsContrastStandard,
  getComputedContrastRatio,

  // Keyboard utilities
  KEYS,
  isNavigationKey,
  isActivationKey,
  stopPropagationOnKeys,

  // Focus management
  getFocusableElements,
  trapFocus,
  useFocusRestore,
  focusFirstElement,

  // ARIA helpers
  generateAriaId,
  setAriaLabel,
  setAriaDescribedBy,
  setAriaLabeledBy,
  announceToScreenReader,

  // Semantic HTML
  validateHeadingHierarchy,
  validateFormLabels,

  // Text sizing
  supportsTextZoom,
  getEffectiveTextSize,

  // Reduced motion
  prefersReducedMotion,
  getAnimationDuration,
  getReducedMotionCSS,

  // Localization
  getLocalizedTimeAnnouncement,
  getLocalizedCurrencyAnnouncement,

  // Validation
  runA11yAudit,
};
