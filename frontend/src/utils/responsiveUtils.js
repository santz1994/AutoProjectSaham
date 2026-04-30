/**
 * Responsive Design Utilities
 * 
 * Shared utilities for responsive design, breakpoints, and device detection
 * Supports mobile-first approach with Jakarta timezone awareness
 */

/**
 * Breakpoint definitions
 * Following Material Design 3 & Tailwind CSS conventions
 */
export const BREAKPOINTS = {
  xs: 0,      // Extra small (mobile)
  sm: 640,    // Small (portrait tablet)
  md: 768,    // Medium (landscape tablet)
  lg: 1024,   // Large (desktop)
  xl: 1280,   // Extra large (large desktop)
  '2xl': 1536 // 2X large (ultra-wide)
};

/**
 * Media query strings for use in CSS-in-JS
 */
export const MEDIA_QUERIES = {
  xs: `(min-width: ${BREAKPOINTS.xs}px)`,
  sm: `(min-width: ${BREAKPOINTS.sm}px)`,
  md: `(min-width: ${BREAKPOINTS.md}px)`,
  lg: `(min-width: ${BREAKPOINTS.lg}px)`,
  xl: `(min-width: ${BREAKPOINTS.xl}px)`,
  '2xl': `(min-width: ${BREAKPOINTS['2xl']}px)`,
  
  // Max width queries for mobile-first
  'max-xs': `(max-width: ${BREAKPOINTS.sm - 1}px)`,
  'max-sm': `(max-width: ${BREAKPOINTS.md - 1}px)`,
  'max-md': `(max-width: ${BREAKPOINTS.lg - 1}px)`,
  'max-lg': `(max-width: ${BREAKPOINTS.xl - 1}px)`,
  'max-xl': `(max-width: ${BREAKPOINTS['2xl'] - 1}px)`,
  
  // Touch queries
  touch: '(hover: none) and (pointer: coarse)',
  noTouch: '(hover: hover) and (pointer: fine)',
  
  // Orientation
  portrait: '(orientation: portrait)',
  landscape: '(orientation: landscape)',
  
  // Prefers reduced motion
  prefersReducedMotion: '(prefers-reduced-motion: reduce)',
  
  // Dark mode
  darkMode: '(prefers-color-scheme: dark)',
  lightMode: '(prefers-color-scheme: light)',
  
  // High DPI (Retina)
  highDPI: '(min-resolution: 2dppx)'
};

function matchMediaSafe(query) {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }

  const result = window.matchMedia(query);
  return Boolean(result && result.matches);
}

/**
 * Get screen size category
 * Useful for responsive logic without hooks required
 */
export function getScreenSize(width) {
  if (width < BREAKPOINTS.sm) return 'xs';
  if (width < BREAKPOINTS.md) return 'sm';
  if (width < BREAKPOINTS.lg) return 'md';
  if (width < BREAKPOINTS.xl) return 'lg';
  if (width < BREAKPOINTS['2xl']) return 'xl';
  return '2xl';
}

/**
 * Check if screen matches breakpoint
 */
export function matchesBreakpoint(width, breakpoint) {
  const breakpointValue = BREAKPOINTS[breakpoint];
  if (breakpointValue === undefined) {
    console.warn(`[responsiveUtils] Unknown breakpoint: ${breakpoint}`);
    return false;
  }
  return width >= breakpointValue;
}

/**
 * Get responsive value based on screen size
 * Useful for dynamic styling without CSS media queries
 * 
 * @example
 * const padding = getResponsiveValue(width, {
 *   xs: '8px',
 *   md: '16px',
 *   lg: '24px'
 * });
 */
export function getResponsiveValue(width, values) {
  const size = getScreenSize(width);
  
  // Try exact match first
  if (values[size]) {
    return values[size];
  }
  
  // Fallback to nearest smaller breakpoint
  const sizes = ['xs', 'sm', 'md', 'lg', 'xl', '2xl'];
  const currentIndex = sizes.indexOf(size);
  
  for (let i = currentIndex; i >= 0; i--) {
    if (values[sizes[i]]) {
      return values[sizes[i]];
    }
  }
  
  // Last resort
  return values.xs || values[Object.keys(values)[0]];
}

/**
 * Touch capabilities detection
 */
export const TOUCH_CAPABILITIES = {
  isTouchDevice: () => {
    if (typeof window === 'undefined') return false;
    
    return (
      ('ontouchstart' in window) ||
      (navigator.maxTouchPoints > 0) ||
      (navigator.msMaxTouchPoints > 0)
    );
  },

  supportsHover: () => {
    if (typeof window === 'undefined') return true;
    return matchMediaSafe('(hover: hover)');
  },

  isCoarsePointer: () => {
    if (typeof window === 'undefined') return false;
    return matchMediaSafe('(pointer: coarse)');
  }
};

/**
 * Device detection utilities
 */
export const DEVICE_DETECTION = {
  /**
   * Detect device type based on user agent
   */
  getDeviceType: () => {
    if (typeof navigator === 'undefined') return 'desktop';
    
    const ua = navigator.userAgent.toLowerCase();
    
    if (/tablet|ipad|playbook|silk|(android(?!.*mobi))/i.test(ua)) {
      return 'tablet';
    }
    if (/mobile|mobi|android|iphone|ipod|blackberry|iemobile|opera mini/i.test(ua)) {
      return 'mobile';
    }
    
    return 'desktop';
  },

  /**
   * Detect if device supports PWA installation
   */
  supportsPWA: () => {
    if (typeof window === 'undefined') return false;
    return 'serviceWorker' in navigator && 'caches' in window;
  },

  /**
   * Detect if app is running in PWA standalone mode
   */
  isStandalone: () => {
    if (typeof window === 'undefined') return false;
    return matchMediaSafe('(display-mode: standalone)') ||
           (navigator.standalone === true);
  },

  /**
   * Get viewport dimensions
   */
  getViewport: () => {
    if (typeof window === 'undefined') {
      return { width: 1024, height: 768, isMobile: false };
    }
    
    const width = window.innerWidth || document.documentElement.clientWidth;
    const height = window.innerHeight || document.documentElement.clientHeight;
    
    return {
      width,
      height,
      isMobile: width < BREAKPOINTS.md,
      isTablet: width >= BREAKPOINTS.md && width < BREAKPOINTS.lg,
      isDesktop: width >= BREAKPOINTS.lg
    };
  },

  /**
   * Get safe area insets (for notched devices)
   */
  getSafeAreaInsets: () => {
    if (typeof CSS === 'undefined' || !CSS.supports) {
      return { top: 0, right: 0, bottom: 0, left: 0 };
    }
    
    const getEnv = (name) => {
      if (CSS.supports(`(bottom: max(0px, env(${name})))`)) {
        const el = document.createElement('div');
        el.style.position = 'fixed';
        el.style.bottom = `max(0px, env(${name}))`;
        document.body.appendChild(el);
        const value = parseInt(
          window.getComputedStyle(el).bottom,
          10
        );
        document.body.removeChild(el);
        return value || 0;
      }
      return 0;
    };
    
    return {
      top: getEnv('safe-area-inset-top'),
      right: getEnv('safe-area-inset-right'),
      bottom: getEnv('safe-area-inset-bottom'),
      left: getEnv('safe-area-inset-left')
    };
  },

  /**
   * Get device capabilities
   */
  getCapabilities: () => {
    if (typeof navigator === 'undefined') {
      return {
        hasGeolocation: false,
        hasCamera: false,
        hasGyroscope: false,
        hasNotification: false,
        hasVibration: false
      };
    }
    
    return {
      hasGeolocation: 'geolocation' in navigator,
      hasCamera: /camera/.test(navigator.mediaDevices),
      hasGyroscope: 'DeviceOrientationEvent' in window,
      hasNotification: 'Notification' in window,
      hasVibration: 'vibrate' in navigator
    };
  }
};

/**
 * Orientation detection utilities
 */
export const ORIENTATION = {
  /**
   * Get current orientation
   */
  getCurrent: () => {
    if (typeof window === 'undefined') return 'portrait';
    return matchMediaSafe('(orientation: portrait)') ? 'portrait' : 'landscape';
  },

  /**
   * Check if portrait
   */
  isPortrait: () => {
    if (typeof window === 'undefined') return true;
    return matchMediaSafe('(orientation: portrait)');
  },

  /**
   * Check if landscape
   */
  isLandscape: () => {
    if (typeof window === 'undefined') return false;
    return matchMediaSafe('(orientation: landscape)');
  }
};

/**
 * Accessibility utilities
 */
export const ACCESSIBILITY = {
  /**
   * Check if user prefers reduced motion
   */
  prefersReducedMotion: () => {
    if (typeof window === 'undefined') return false;
    return matchMediaSafe('(prefers-reduced-motion: reduce)') ||
           navigator.userAgentData?.mobile === true;
  },

  /**
   * Check if dark mode is preferred
   */
  prefersDarkMode: () => {
    if (typeof window === 'undefined') return false;
    return matchMediaSafe('(prefers-color-scheme: dark)');
  },

  /**
   * Check if high contrast is preferred
   */
  prefersHighContrast: () => {
    if (typeof window === 'undefined') return false;
    return matchMediaSafe('(prefers-contrast: more)');
  },

  /**
   * Get preferred color scheme
   */
  getColorScheme: () => {
    if (typeof window === 'undefined') return 'light';
    return matchMediaSafe('(prefers-color-scheme: dark)') ? 'dark' : 'light';
  }
};

/**
 * Format utilities for responsive design
 */
export const FORMAT = {
  /**
   * Format number for display on screen size
   * Useful for large numbers on small screens
   */
  formatCompactNumber: (num, width) => {
    if (width < BREAKPOINTS.sm || num < 1000) {
      return num.toString();
    }
    
    if (num >= 1_000_000) {
      return (num / 1_000_000).toFixed(1) + 'M';
    }
    if (num >= 1_000) {
      return (num / 1_000).toFixed(1) + 'K';
    }
    
    return num.toString();
  },

  /**
   * Truncate text for mobile display
   */
  truncateForMobile: (text, width, mobileLength = 20, desktopLength = 50) => {
    const maxLength = width < BREAKPOINTS.md ? mobileLength : desktopLength;
    if (text.length > maxLength) {
      return text.substring(0, maxLength) + '...';
    }
    return text;
  },

  /**
   * Format number of columns for grid based on width
   */
  getGridColumns: (width, options = {}) => {
    const {
      minColumns = 1,
      maxColumns = 4,
      mobileColumns = 1,
      tabletColumns = 2,
      desktopColumns = 3
    } = options;
    
    if (width < BREAKPOINTS.md) {
      return Math.max(minColumns, Math.min(maxColumns, mobileColumns));
    }
    if (width < BREAKPOINTS.lg) {
      return Math.max(minColumns, Math.min(maxColumns, tabletColumns));
    }
    return Math.max(minColumns, Math.min(maxColumns, desktopColumns));
  }
};

/**
 * Jakarta Timezone utilities (IDX compliance)
 */
export const JAKARTA_TZ = {
  /**
   * Get current time in Jakarta (WIB: UTC+7)
   */
  now: () => {
    return new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Jakarta' }));
  },

  /**
   * Format date for Jakarta timezone
   */
  format: (dateOrFormat = new Date(), format = 'HH:mm:ss') => {
    let date = dateOrFormat;
    if (typeof dateOrFormat === 'string') {
      format = dateOrFormat;
      date = new Date();
    }

    const jakartaDate = new Date(
      date.toLocaleString('en-US', { timeZone: 'Asia/Jakarta' })
    );
    
    // Simple format (can be extended with more options)
    const hours = String(jakartaDate.getHours()).padStart(2, '0');
    const minutes = String(jakartaDate.getMinutes()).padStart(2, '0');
    const seconds = String(jakartaDate.getSeconds()).padStart(2, '0');
    
    if (format === 'HH:mm:ss') return `${hours}:${minutes}:${seconds}`;
    if (format === 'HH:mm') return `${hours}:${minutes}`;
    
    return jakartaDate.toString();
  },

  /**
   * Check if current time is within BEI trading hours (09:30-16:00 WIB)
   */
  isInsideBEIHours: (date = new Date()) => {
    const jakartaDate = new Date(
      date.toLocaleString('en-US', { timeZone: 'Asia/Jakarta' })
    );
    
    const hours = jakartaDate.getHours();
    const minutes = jakartaDate.getMinutes();
    const day = jakartaDate.getDay();
    
    // Monday-Friday only (1-5)
    if (day === 0 || day === 6) {
      return false; // Weekend
    }
    
    const timeInMinutes = hours * 60 + minutes;
    const openTime = 9 * 60 + 30; // 09:30
    const closeTime = 16 * 60;     // 16:00
    
    return timeInMinutes >= openTime && timeInMinutes < closeTime;
  }
};

export default {
  BREAKPOINTS,
  MEDIA_QUERIES,
  getScreenSize,
  matchesBreakpoint,
  getResponsiveValue,
  TOUCH_CAPABILITIES,
  DEVICE_DETECTION,
  ORIENTATION,
  ACCESSIBILITY,
  FORMAT,
  JAKARTA_TZ
};
