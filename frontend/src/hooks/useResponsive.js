/**
 * Custom Hook: useResponsive
 * 
 * Provides responsive design detection and utilities for React components
 * Includes breakpoint matching, device detection, and accessibility preferences
 * 
 * Usage:
 * ```jsx
 * const { 
 *   width, 
 *   height, 
 *   isMobile, 
 *   isTablet,
 *   matchBreakpoint,
 *   deviceType,
 *   isStandalone,
 *   darkMode,
 *   reducedMotion
 * } = useResponsive();
 * ```
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  BREAKPOINTS,
  getScreenSize,
  matchesBreakpoint,
  getResponsiveValue,
  TOUCH_CAPABILITIES,
  DEVICE_DETECTION,
  ORIENTATION,
  ACCESSIBILITY
} from '../utils/responsiveUtils';

export const useResponsive = () => {
  // Viewport dimensions
  const [width, setWidth] = useState(() => {
    return typeof window !== 'undefined' ? window.innerWidth : 1024;
  });

  const [height, setHeight] = useState(() => {
    return typeof window !== 'undefined' ? window.innerHeight : 768;
  });

  // Device info
  const [deviceType, setDeviceType] = useState(() =>
    DEVICE_DETECTION.getDeviceType()
  );

  const [isStandalone, setIsStandalone] = useState(() =>
    DEVICE_DETECTION.isStandalone()
  );

  // Capabilities
  const [capabilities, setCapabilities] = useState(() =>
    DEVICE_DETECTION.getCapabilities()
  );

  const [isTouchDevice, setIsTouchDevice] = useState(() =>
    TOUCH_CAPABILITIES.isTouchDevice()
  );

  const [supportsHover, setSupportsHover] = useState(() =>
    TOUCH_CAPABILITIES.supportsHover()
  );

  // Orientation
  const [orientation, setOrientation] = useState(() =>
    ORIENTATION.getCurrent()
  );

  // Accessibility preferences
  const [darkMode, setDarkMode] = useState(() =>
    ACCESSIBILITY.prefersDarkMode()
  );

  const [reducedMotion, setReducedMotion] = useState(() =>
    ACCESSIBILITY.prefersReducedMotion()
  );

  const [highContrast, setHighContrast] = useState(() =>
    ACCESSIBILITY.prefersHighContrast()
  );

  // Safe area insets for notched devices
  const [safeAreaInsets, setSafeAreaInsets] = useState(() =>
    DEVICE_DETECTION.getSafeAreaInsets()
  );

  // Debounce resize handler
  const resizeTimeoutRef = useRef(null);
  const mediaQueryListsRef = useRef([]);

  /**
   * Handle window resize with debounce
   */
  const handleResize = useCallback(() => {
    if (typeof window === 'undefined') return;

    if (resizeTimeoutRef.current) {
      clearTimeout(resizeTimeoutRef.current);
    }

    resizeTimeoutRef.current = setTimeout(() => {
      setWidth(window.innerWidth);
      setHeight(window.innerHeight);
      setSafeAreaInsets(DEVICE_DETECTION.getSafeAreaInsets());
      setOrientation(ORIENTATION.getCurrent());
    }, 150); // 150ms debounce
  }, []);

  /**
   * Handle media query changes
   */
  const handleMediaQueryChange = useCallback((event) => {
    if (event.media.includes('hover')) {
      setSupportsHover(event.matches);
    } else if (event.media.includes('prefers-color-scheme')) {
      setDarkMode(event.media.includes('dark') ? event.matches : !event.matches);
    } else if (event.media.includes('prefers-reduced-motion')) {
      setReducedMotion(event.matches);
    } else if (event.media.includes('prefers-contrast')) {
      setHighContrast(event.matches);
    }
  }, []);

  /**
   * Setup event listeners on mount
   */
  useEffect(() => {
    if (typeof window === 'undefined') return;

    // Resize listener
    window.addEventListener('resize', handleResize, { passive: true });

    // Media query listeners for accessibility preferences
    const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const highContrastQuery = window.matchMedia('(prefers-contrast: more)');
    const hoverQuery = window.matchMedia('(hover: hover)');

    mediaQueryListsRef.current = [
      darkModeQuery,
      reducedMotionQuery,
      highContrastQuery,
      hoverQuery
    ];

    // Modern browsers
    if (darkModeQuery.addListener) {
      darkModeQuery.addListener(handleMediaQueryChange);
      reducedMotionQuery.addListener(handleMediaQueryChange);
      highContrastQuery.addListener(handleMediaQueryChange);
      hoverQuery.addListener(handleMediaQueryChange);
    } else {
      // Newer browsers
      darkModeQuery.addEventListener('change', handleMediaQueryChange);
      reducedMotionQuery.addEventListener('change', handleMediaQueryChange);
      highContrastQuery.addEventListener('change', handleMediaQueryChange);
      hoverQuery.addEventListener('change', handleMediaQueryChange);
    }

    return () => {
      // Cleanup
      window.removeEventListener('resize', handleResize);

      mediaQueryListsRef.current.forEach((query) => {
        if (query.removeListener) {
          query.removeListener(handleMediaQueryChange);
        } else {
          query.removeEventListener('change', handleMediaQueryChange);
        }
      });

      if (resizeTimeoutRef.current) {
        clearTimeout(resizeTimeoutRef.current);
      }
    };
  }, [handleResize, handleMediaQueryChange]);

  /**
   * Get screen size category (xs, sm, md, lg, xl, 2xl)
   */
  const getSize = useCallback(() => getScreenSize(width), [width]);

  /**
   * Check if width matches a breakpoint
   */
  const matches = useCallback((breakpoint) => matchesBreakpoint(width, breakpoint), [width]);

  /**
   * Get responsive value based on current width
   */
  const getResponsive = useCallback((values) => getResponsiveValue(width, values), [width]);

  /**
   * Computed properties for common breakpoints
   */
  const isMobile = width < BREAKPOINTS.md;
  const isTablet = width >= BREAKPOINTS.md && width < BREAKPOINTS.lg;
  const isDesktop = width >= BREAKPOINTS.lg;
  const isLargeDesktop = width >= BREAKPOINTS.xl;

  /**
   * CSS-ready safe area variables
   */
  const cssVariables = {
    '--safe-area-top': `${safeAreaInsets.top}px`,
    '--safe-area-right': `${safeAreaInsets.right}px`,
    '--safe-area-bottom': `${safeAreaInsets.bottom}px`,
    '--safe-area-left': `${safeAreaInsets.left}px`,
    '--viewport-width': `${width}px`,
    '--viewport-height': `${height}px`
  };

  return {
    // Dimensions
    width,
    height,
    viewport: {
      width,
      height,
      isMobile,
      isTablet,
      isDesktop,
      isLargeDesktop
    },

    // Breakpoint checks
    isMobile,
    isTablet,
    isDesktop,
    isLargeDesktop,
    getSize,
    matches,
    matchBreakpoint: matches, // Alias

    // Responsive values
    getResponsive,

    // Device info
    deviceType,
    isStandalone,
    isTouchDevice,
    supportsHover,
    capabilities,

    // Orientation
    orientation,
    isPortrait: orientation === 'portrait',
    isLandscape: orientation === 'landscape',

    // Accessibility
    darkMode,
    reducedMotion,
    highContrast,
    colorScheme: darkMode ? 'dark' : 'light',

    // Safe area (for notched devices)
    safeAreaInsets,
    cssVariables
  };
};

export default useResponsive;
