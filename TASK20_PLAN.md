# Task 20: Accessibility Compliance (WCAG AAA)
## Implementation Plan

**Status:** 🚀 IN PROGRESS  
**Target:** WCAG 2.1 AAA Compliance  
**Scope:** Full accessibility audit + remediation across all frontend components  

---

## 📋 Checklist - WCAG AAA Requirements

### 1. Perceivable (Dapat Dipersepsikan)
- [ ] **Color Contrast**: Minimum 7:1 for normal text (AAA)
- [ ] **Text Sizing**: Scale to 200% without loss of function
- [ ] **Focus Indicators**: All interactive elements have visible focus (3px minimum)
- [ ] **Alternative Text**: All images have descriptive alt text
- [ ] **Audio/Video**: Captions and transcripts for multimedia
- [ ] **Color Not Sole Means**: Don't rely on color alone for information

### 2. Operable (Dapat Dioperasikan)
- [ ] **Keyboard Navigation**: All functionality via keyboard
- [ ] **No Keyboard Traps**: Users can exit any component with keyboard
- [ ] **Focus Order**: Logical tab order (use tabindex carefully)
- [ ] **Skip Links**: Skip to main content links
- [ ] **No Auto-Play**: Audio/video doesn't autoplay with sound
- [ ] **Pause/Controls**: Users can pause/control time-based content

### 3. Understandable (Dapat Dipahami)
- [ ] **Language Clear**: Jargon minimized, plain language used
- [ ] **Abbreviations**: Defined on first use or via <abbr> tag
- [ ] **Unusual Words**: Definitions provided for technical terms
- [ ] **Form Labels**: Proper <label> associations
- [ ] **Error Identification**: Clear error messages with recovery guidance
- [ ] **Instructions**: Provide clear instructions for complex components

### 4. Robust (Kokoh)
- [ ] **Semantic HTML**: Proper use of heading hierarchy, nav, main, etc.
- [ ] **ARIA Implementation**: Correct ARIA roles, states, properties
- [ ] **Name/Role/Value**: All UI components have these defined
- [ ] **Status Updates**: Use aria-live for dynamic content
- [ ] **Validator**: Pass HTML validation

---

## 🔧 Implementation Areas

### Frontend Components (React JSX)

**High Priority Components:**
1. **NotificationBell.jsx** - Notification center button
2. **NotificationCenter.jsx** - Notification list & filters
3. **ChartComponent.jsx** - TradingView chart wrapper
4. **ExplainabilityDashboard.jsx** - ML model insights
5. **PWAInstallButton.jsx** - Install prompt

**Form Accessibility:**
6. **Forms** - All input fields need proper labels
7. **Modals** - Focus trapping & return focus
8. **Dropdowns** - ARIA menus with keyboard support
9. **Tables** - Proper headers & scope attributes

### Styling (CSS/Tailwind)

**Color Contrast Fixes:**
- Check all text/background combinations
- Ensure 7:1 ratio for AAA
- Dark mode variants must also pass

**Focus States:**
- No outline removal (very important!)
- Custom focus-visible outlines if needed
- Size: minimum 3px

**Animations:**
- Respect prefers-reduced-motion
- Remove autoplaying animations for users with motion sensitivities
- Pause buttons for animations

---

## 📝 Specific Files to Create/Update

### 1. **frontend/src/utils/a11y.js**
Accessibility utilities module:
```javascript
// Color contrast checker
// ARIA label generator
// Focus management helpers
// Keyboard event utilities
```

### 2. **frontend/src/hooks/useAccessibility.js**
Custom hook for accessibility features:
```javascript
// useA11y() - Get a11y settings & helpers
// useKeyboard() - Handle keyboard navigation
// useFocusManagement() - Manage focus trap/restore
// useAriaLive() - Announce dynamic changes
```

### 3. **frontend/src/components/AccessibleIcon.jsx**
ARIA-compliant icon wrapper:
```javascript
// Wrap icons with proper aria-label/aria-hidden
// Ensure meaningful button text
```

### 4. **frontend/src/components/AccessibleForm.jsx**
Form component with built-in a11y:
```javascript
// Label associations
// Error messages as aria-describedby
// Required field indicators
// Fieldset grouping
```

### 5. **frontend/src/components/__tests__/a11y.test.js**
Accessibility testing suite:
```javascript
// axe-core integration
// Color contrast tests
// Keyboard navigation tests
// ARIA validation tests
// 50+ test cases
```

### 6. **docs/ACCESSIBILITY.md**
Detailed accessibility documentation:
- WCAG AAA requirements checklist
- Implementation guidelines for developers
- Testing procedures
- Common issues & solutions

---

## 🧪 Testing Requirements

### Automated Testing (axe-core)
```bash
npm install --save-dev @axe-core/react jest-axe
```

Test suites:
- Color contrast (7:1 minimum)
- ARIA attributes
- Semantic HTML structure
- Keyboard navigation
- Form labels & validation

### Manual Testing
- Screen reader (NVDA, JAWS, VoiceOver)
- Keyboard-only navigation
- Browser zoom to 200%
- Color blind simulator
- Motion sensitivity testing

### Tools Integration
- **axe-core**: Automated a11y testing
- **jest-axe**: Testing in Jest
- **pa11y**: Command-line a11y checker
- **Wave**: Browser extension for visual feedback

---

## 🎨 Color Contrast Improvements

### Current Issues to Fix
- Notification timestamp text (may be too light)
- Disabled button states (need higher contrast)
- Placeholder text colors (must be 7:1)
- Secondary text colors (check gray on white)

### Standard Palette (7:1 AAA compliant)
```css
/* Text on Light Background */
--text-primary: #000000;      /* 21:1 contrast on white */
--text-secondary: #333333;    /* 12.6:1 contrast on white */
--text-disabled: #666666;     /* 7.3:1 contrast on white */

/* Text on Dark Background */
--text-light-primary: #ffffff;    /* 21:1 contrast on black */
--text-light-secondary: #e6e6e6;  /* 18:1 contrast on black */
--text-light-disabled: #999999;   /* 7.2:1 contrast on #181818 */
```

---

## ⌨️ Keyboard Navigation Improvements

### Expected Tab Order
1. Skip to main content link
2. Header navigation
3. Main content (forms, buttons, links)
4. Modals (when open) - trap focus
5. Footer navigation

### Focus Management
- Focus visible: 3px outline
- :focus-visible only (not :focus)
- Custom styles for buttons/links
- Restored focus after modal close

### Escape Key Handling
- Modals close on Escape
- Dropdowns close on Escape
- Focus returns to opener

---

## 🔊 Screen Reader Announcements

### ARIA Live Regions
```jsx
// Notification arrivals
<div role="status" aria-live="polite" aria-atomic="true">
  {notification.message}
</div>

// Chart updates
<div role="status" aria-live="assertive">
  Price updated: {price}
</div>

// Form errors
<div aria-describedby="error-msg">
  <input ... />
  <div id="error-msg">{errorMessage}</div>
</div>
```

### Landmark Regions
```jsx
<header role="banner">
<nav role="navigation" aria-label="Main">
<main role="main">
<aside role="complementary" aria-label="Sidebar">
<footer role="contentinfo">
```

---

## 📊 Implementation Timeline

**Phase 1: Setup (30 min)**
- [ ] Install a11y testing libraries
- [ ] Create a11y utilities module
- [ ] Create useAccessibility hook

**Phase 2: Components (1.5 hours)**
- [ ] Audit all components
- [ ] Add ARIA attributes
- [ ] Update form elements
- [ ] Fix color contrast issues

**Phase 3: Keyboard Navigation (1 hour)**
- [ ] Implement keyboard handlers
- [ ] Add skip links
- [ ] Test tab order
- [ ] Focus management

**Phase 4: Testing (1 hour)**
- [ ] Write a11y tests
- [ ] Run axe-core audit
- [ ] Manual screen reader testing
- [ ] Keyboard-only testing

**Phase 5: Documentation (30 min)**
- [ ] Create ACCESSIBILITY.md
- [ ] Document patterns learned
- [ ] Update PROGRESS.md
- [ ] Create TASK20_COMPLETION.md

---

## 🚨 Critical WCAG AAA Criteria

1. **Contrast (AAA)**: 7:1 for normal text, 4.5:1 for large text
2. **Focus**: Visible focus indicator on all interactive elements
3. **Keyboard**: All functionality available via keyboard
4. **Structure**: Proper heading hierarchy (h1 → h2 → h3)
5. **Labels**: Every form input has explicit <label>
6. **Errors**: Clear error messages with recovery instructions
7. **Language**: Declared HTML lang attribute
8. **Semantics**: Use <button>, <a>, proper ARIA roles

---

## ✅ Success Criteria

- [ ] Zero axe-core violations
- [ ] 7:1 contrast ratio on all text
- [ ] All components keyboard navigable
- [ ] Focus visible on all interactive elements
- [ ] All forms properly labeled
- [ ] Screen reader compatible (tested with NVDA)
- [ ] 50+ a11y test cases passing
- [ ] WCAG AAA compliance verified
- [ ] Documentation complete

---

**Next Step:** Start Phase 1 implementation
