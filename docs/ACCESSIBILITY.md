# 📋 Accessibility Guidelines & Documentation
## WCAG 2.1 AAA Compliance Framework

**Document Version:** 1.0  
**Last Updated:** 2026-04-01 UTC+7 (JAKARTA TIME)  
**Status:** ✅ PRODUCTION READY

---

## Table of Contents

1. [Overview](#overview)
2. [WCAG 2.1 AAA Requirements](#wcag-21-aaa-requirements)
3. [Implementation Guidelines](#implementation-guidelines)
4. [Testing Procedures](#testing-procedures)
5. [Common Issues & Solutions](#common-issues--solutions)
6. [Accessibility Utilities API](#accessibility-utilities-api)
7. [Indonesia-Specific Considerations](#indonesia-specific-considerations)
8. [Compliance Checklist](#compliance-checklist)

---

## Overview

AutoSaham is committed to providing an **accessible, inclusive digital experience** for all users, including those with disabilities. This document defines accessibility standards and provides implementation guidance for developers.

### Why Accessibility Matters

- **Legal**: WCAG 2.1 is internationally recognized standard
- **Ethical**: Excludes no users based on ability
- **Business**: Improves SEO, usability for all users
- **Market**: Indonesian government increasingly requires (WCAG compliance)

### Scope

This guide covers:
- Web interface (React frontend)
- Desktop application (Python backend)
- Mobile-responsive design (PWA)
- All user interactions (forms, notifications, charts, alerts)

---

## WCAG 2.1 AAA Requirements

### Level AAA is the Highest Compliance Level

WCAG defines 3 levels:
- **A**: Basic requirements (4.5:1 contrast, keyboard navigation)
- **AA**: Enhanced requirements (7:1 contrast for all text)
- **AAA**: Enhanced+ requirements (7:1 minimum for ALL text, 5:1 for graphics)

We implement **AAA** for critical paths (notifications, trading signals, forms).

### Four Pillars: POUR Framework

#### 1. **Perceivable** - Users can see/hear content

✅ **Color Contrast - 7:1 (AAA)**
```
Primary Text on Light: #000000 on #ffffff → 21:1
Secondary Text:       #333333 on #ffffff → 12.6:1
Disabled Text:        #666666 on #ffffff → 7.3:1

All meet AAA 7:1 minimum
```

✅ **Text Sizing - 200% Zoom Support**
- Text must scale to 200% without loss of function
- Use relative units (rem, em) not px
- No horizontal scrolling at 200% zoom

✅ **Alternative Text (Alt Text)**
- Icons: Provide aria-label
- Images: Describe content precisely
- Charts: Provide data table fallback

✅ **Captions & Transcripts**
- Video: CC/subtitles required
- Audio: Transcript required
- Complex visuals: Text description required

#### 2. **Operable** - Users can control & navigate

✅ **Keyboard Navigation - 100% of functionality**
```
Tab:       Move to next interactive element
Shift+Tab: Move to previous element
Enter:     Activate button/link/form control
Space:     Activate checkbox/radio/button
Escape:    Close modal/dropdown
Arrow Keys: Navigate lists/menus/sliders
Home/End:  First/last item in list

NO KEYBOARD TRAPS: Users can always escape with Escape key
```

✅ **Focus Visible - 3px minimum outline**
```css
button:focus-visible {
  outline: 3px solid #4a90e2;
  outline-offset: 2px;
}
```

✅ **Skip Links - First element on page**
```html
<a href="#main" class="skip-to-main-content">
  Skip to main content
</a>
```

✅ **Touch Targets - Minimum 44x44px**
- Mobile: Buttons/links at least 44x44px
- Prevents accidental clicks
- Helps users with motor impairments

✅ **No Auto-play**
- Video/audio don't auto-play
- Animations respect prefers-reduced-motion
- Users control when content plays

#### 3. **Understandable** - Users comprehend content

✅ **Clear Language**
- Plain language, minimize jargon
- Short sentences (15-20 words)
- Define technical terms on first use
- Indonesian (Bahasa Indonesia) primary language

✅ **Proper Form Labels**
```html
<!-- CORRECT -->
<label for="email">Email Address</label>
<input id="email" type="email" required />
<span class="error" id="email-error">Invalid email format</span>
<input aria-describedby="email-error" />

<!-- WRONG -->
<input type="email" placeholder="Enter email" />
```

✅ **Error Messages - Clear & Helpful**
```
❌ "Error"
✅ "Email must be in format: user@example.com"
```

✅ **Instructions - Explicit & Available**
- Before critical operations
- Clear steps with examples
- Available in Indonesian

#### 4. **Robust** - Compatible with assistive technology

✅ **Semantic HTML**
```html
<!-- Structure matters -->
<header>
<nav role="navigation">
<main role="main">
<section>
<article>
<aside role="complementary">
<footer role="contentinfo">
```

✅ **ARIA Implementation**
```jsx
<!-- Buttons without text need aria-label -->
<button aria-label="Close notification">×</button>

<!-- Form inputs need labels -->
<input aria-label="Stock symbol" />

<!-- Live regions for dynamic updates -->
<div role="status" aria-live="polite">
  Price updated: Rp 15,500
</div>

<!-- Expanded states -->
<button aria-expanded="false" aria-controls="menu">Menu</button>
```

✅ **Passing HTML Validation**
- Semantic elements used correctly
- No duplicate IDs
- Proper element nesting

---

## Implementation Guidelines

### Frontend Components (React)

#### 1. Buttons

```jsx
// ✅ CORRECT
<button onClick={handleClick}>Save Trade</button>

// ✅ CORRECT - Icon only
<button aria-label="Close notification" onClick={close}>
  ×
</button>

// ❌ WRONG - No accessible name
<button onClick={delete} style={{ background: 'red' }} />

// ❌ WRONG - Color as only indicator
<button style={{ color: errorColor, border: 'none' }}>Delete</button>
```

#### 2. Forms

```jsx
// ✅ CORRECT
<div>
  <label htmlFor="quantity">Quantity (shares)</label>
  <input
    id="quantity"
    type="number"
    min="1"
    max="1000"
    required
    aria-invalid={hasError}
    aria-describedby={hasError ? "qty-error" : undefined}
  />
  {hasError && <span id="qty-error" role="alert">
    Quantity must be between 1 and 1,000
  </span>}
</div>

// ❌ WRONG
<input type="number" placeholder="Qty" />
```

#### 3. Modals

```jsx
{/* ✅ CORRECT */}
<div role="dialog" aria-modal="true" aria-labelledby="dialog-title">
  <h2 id="dialog-title">Confirm Trade</h2>
  <p>Are you sure you want to sell 100 BBCA.JK shares?</p>
  <button onClick={confirm}>Yes, Confirm</button>
  <button onClick={close}>Cancel</button>
</div>

// Focus trapped in modal
// Focus restored to opener when modal closes
```

#### 4. Lists & Menus

```jsx
// ✅ CORRECT
<ul role="menubar">
  {items.map((item, index) => (
    <li key={item.id} role="none">
      <button
        role="menuitem"
        aria-expanded={expanded === index}
        onClick={() => toggleItem(index)}
      >
        {item.label}
      </button>
      {expanded === index && (
        <ul role="menu">
          {item.submenu.map(sub => (
            <li key={sub.id}><a href={sub.url}>{sub.label}</a></li>
          ))}
        </ul>
      )}
    </li>
  ))}
</ul>
```

#### 5. Notifications

```jsx
// ✅ CORRECT
<div role="alert" aria-live="assertive">
  Order placed successfully! Order #12345
</div>

<div role="status" aria-live="polite">
  Updating price data... Do not refresh
</div>

// ❌ WRONG
<div className="notification">Order placed!</div>
```

#### 6. Charts & Data Visualization

```jsx
// ✅ CORRECT - Provide accessible alternative
<div>
  <h2>BBCA.JK Price History</h2>
  
  {/* Chart for sighted users */}
  <ChartComponent data={prices} role="presentation" />
  
  {/* Table for screen reader users */}
  <table className="sr-only">
    <thead>
      <tr>
        <th>Date</th>
        <th>Open</th>
        <th>High</th>
        <th>Low</th>
        <th>Close</th>
      </tr>
    </thead>
    <tbody>
      {prices.map(price => (
        <tr key={price.date}>
          <td>{formatDate(price.date)}</td>
          <td>Rp {formatCurrency(price.open)}</td>
          {/* ... */}
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

### Backend (Python)

#### API Error Responses

```python
# ✅ CORRECT - Clear, actionable error
{
  "error": "Invalid order quantity",
  "details": "Quantity must be between 1 and 1,000 shares",
  "field": "quantity",
  "code": "VALIDATION_ERROR"
}

# ❌ WRONG
{ "error": "Invalid input" }
```

#### Timestamps in All Zones

```python
from datetime import datetime
import pytz

# ✅ Always include Jakarta time in responses
jakarta_tz = pytz.timezone('Asia/Jakarta')
now = datetime.now(jakarta_tz)

response = {
  "timestamp": now.isoformat(),
  "timestamp_wib": now.strftime("%Y-%m-%d %H:%M:%S WIB"),
  "price": 15500
}
```

---

## Testing Procedures

### Automated Testing

#### 1. **axe-core Integration**

```bash
npm install --save-dev @axe-core/react jest-axe
```

```jsx
import { axe, toHaveNoViolations } from 'jest-axe';

describe('NotificationBell accessibility', () => {
  test('should not have accessibility violations', async () => {
    const { container } = render(<NotificationBell />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
```

#### 2. **Lighthouse Audit**

```bash
# Chrome DevTools: Lighthouse tab
# Target: Accessibility score ≥ 95
# Automated in CI: npm run lighthouse
```

#### 3. **HTML Validation**

```bash
npm install --save-dev @html-validate/cli

# Check semantic HTML
html-validate frontend/src/components/**/*.jsx
```

### Manual Testing

#### Screen Reader Testing

**Windows: NVDA (Free)**
```
1. Download: https://www.nvaccess.org/download/
2. Install & launch
3. Open AutoSaham in Firefox
4. Enable screen reader: NVDA key + Z
5. Navigate with Tab, arrow keys, Enter
6. Verify all elements announced properly
```

**macOS: VoiceOver (Built-in)**
```
1. System Preferences → Accessibility → VoiceOver
2. Enable with Cmd + F5
3. Navigate with VO key (Ctrl + Opt)
4. Test with Safari browser
```

**Testing Checklist:**
- [ ] All buttons have accessible names
- [ ] Form labels associated with inputs
- [ ] Heading hierarchy announced correctly
- [ ] Images have alt text announced
- [ ] Live regions announce updates
- [ ] Links described by text/aria-label
- [ ] Form errors clearly stated
- [ ] All interactive elements reachable

#### Keyboard-Only Testing

Disable mouse, use Tab to navigate:
```
1. Unplug mouse / disable trackpad
2. Press Tab: Navigate forward
3. Press Shift+Tab: Navigate backward
4. Press Enter/Space: Activate
5. Press Escape: Close modals
6. Press Arrow keys: Navigate lists

✓ Can reach all interactive elements
✓ No keyboard traps (can escape all components)
✓ Focus visible on all elements
✓ Tab order is logical
❌ Should not need arrow keys in form (except date pickers)
```

#### Color Blind Testing

Use browser extension or color specifications:
```
Tools:
- Color Blind (Chrome extension)
- Sim Daltonism (macOS app)
- Coblis (Web-based)

Test with simulator set to:
1. Protanopia (red-blind)
2. Deuteranopia (green-blind)
3. Tritanopia (blue-yellow-blind)
4. Achromatomaly (total color-blind)

Verify:
✓ All information visible even without color
✓ Buttons/alerts identifiable (not just colored)
✓ Charts/data distinguishable
```

#### Text Sizing Test

```
Browser: Zoom to 200% (Ctrl + '+')
✓ Text legible (no tiny text)
✓ No horizontal scrollbars
✓ All interactive elements reachable
✓ Layout doesn't break
✓ Modals remain accessible
```

#### Motion Sensitivity Test

```
System settings → Accessibility → Display
Enable: "Reduce motion"

✓ Animations don't play (or reduced to instant)
✓ Transitions don't play (or reduced to instant)
✓ Content still accessible
✓ Functionality not impaired
```

---

## Common Issues & Solutions

### Issue 1: Missing Focus Indicator

**Problem:** Can't see where keyboard focus is

```css
/* ❌ WRONG */
button:focus {
  outline: none;
}

/* ✅ CORRECT */
button:focus-visible {
  outline: 3px solid #4a90e2;
  outline-offset: 2px;
}
```

### Issue 2: Color Alone Indicates Status

**Problem:** Red button = error, but colorblind user can't tell

```jsx
/* ❌ WRONG */
<button style={{ color: 'red' }}>Delete</button>

/* ✅ CORRECT */
<button style={{ color: 'red' }} aria-label="Delete (destructive action)">
  🗑️ Delete
</button>
```

### Issue 3: Form Input Without Label

**Problem:** Screen reader user can't understand what input is for

```jsx
/* ❌ WRONG */
<input placeholder="Enter quantity" />

/* ✅ CORRECT */
<label htmlFor="qty">Quantity (shares)</label>
<input id="qty" placeholder="e.g., 100" />
```

### Issue 4: Icon-Only Buttons

**Problem:** Screen reader says "button" with no label

```jsx
/* ❌ WRONG */
<button>×</button>

/* ✅ CORRECT */
<button aria-label="Close notification">×</button>
```

### Issue 5: No Skip Links

**Problem:** Keyboard user has to tab through entire navigation

```html
<!-- ✅ CORRECT - First element on page -->
<a href="#main" className="skip-to-main-content">
  Skip to main content
</a>

<nav><!-- Navigation items --></nav>

<main id="main"><!-- Main content --></main>
```

### Issue 6: Auto-Playing Animations

**Problem:** User with vestibular disorder gets nauseated

```jsx
/* ❌ WRONG */
<motion.div animate={{ rotate: 360 }} transition={{ duration: 2 }} />

/* ✅ CORRECT */
const { prefersReducedMotion } = useReducedMotion();

<motion.div
  animate={{ rotate: prefersReducedMotion ? 0 : 360 }}
  transition={{ duration: prefersReducedMotion ? 0 : 2 }}
/>
```

### Issue 7: Complex Charts Without Alternative

**Problem:** Screen reader user can't access chart data

```jsx
/* ✅ CORRECT - Always provide fallback */
<div>
  <ChartComponent data={prices} role="presentation" />
  
  <table className="sr-only">
    {/* Data in table format for assistive tech */}
  </table>
</div>
```

---

## Accessibility Utilities API

### Color Contrast

```javascript
import a11y from './utils/a11y';

// Get contrast ratio between two colors
const ratio = a11y.getContrastRatio('#000000', '#ffffff');
// 21

// Check if meets WCAG standard
const meetsAAA = a11y.meetsContrastStandard(ratio, 'AAA', 'normal');
// true
```

### Keyboard Navigation

```javascript
// Check if key is Enter or Space
if (a11y.isActivationKey(event)) {
  handleActivation();
}

// Check if key is Arrow or Home/End
if (a11y.isNavigationKey(event)) {
  handleNavigation();
}
```

### Focus Management

```javascript
const a11y = useAccessibility({
  trapFocus: true,  // Modal focus trap
  autoFocusFirst: true,  // Auto-focus first element
  onEscape: handleClose,  // Close on Escape
});

// Manual focus control
a11y.focusFirst(); // Focus first focusable element
a11y.focusLast();  // Focus last focusable element
```

### ARIA Helpers

```javascript
// Announce to screen readers
a11y.announce('Order placed successfully!', 'assertive');

// Generate unique IDs
const errorId = a11y.generateAriaId('error');

// Set ARIA relationships
a11y.setAriaDescribedBy(input, errorId);
a11y.setAriaLabeledBy(input, labelId);
```

---

## Indonesia-Specific Considerations

### Language (Bahasa Indonesia)

✅ **Primary language is Indonesian**
```html
<html lang="id-ID">
```

✅ **Translated error messages & announcements**
```javascript
const messages = {
  success: 'Pembelian berhasil! Pesanan #{orderId}',
  error: 'Gagal memproses pesanan. Silahkan coba lagi.',
  validation: 'Kuantitas harus antara 1 dan 1,000 saham',
};
```

### Timezone (Asia/Jakarta / WIB)

✅ **All timestamps in Jakarta timezone**
```python
jakarta_tz = pytz.timezone('Asia/Jakarta')
now = datetime.now(jakarta_tz)
# 2026-04-01 17:30:00+07:00 (WIB)
```

✅ **Screen reader announcements include timezone context**
```javascript
const announcement = useJakartaTime(date);
// "Time in Jakarta: 1 April 2026, 17:30 WIB"
```

### Currency (Indonesian Rupiah / IDR)

✅ **Announce amounts in IDR with proper formatting**
```javascript
const { formatted } = useLocalizedCurrency(15000);
// "Rp 15.000"

const announcement = useLocalizedCurrencyAnnouncement(15000);
// "Rp 15,000" (for screen reader)
```

### Trading Rules (BEI / Indonesia Stock Exchange)

✅ **Communicate trading hours & rules clearly**
```
Market Hours: 09:30 - 16:00 WIB (Monday-Friday)
Outside hours: Orders held until market opens
Holidays: Respect Indonesian public holidays (libur BEI)
```

---

## Compliance Checklist

### Phase 1: Foundation ✅

- [ ] All buttons have accessible names
- [ ] All form inputs have labels
- [ ] Color contrast ≥ 7:1 (AAA)
- [ ] Keyboard navigation works
- [ ] Focus visible on all elements
- [ ] No keyboard traps

### Phase 2: Enhancement

- [ ] Skip links functional
- [ ] ARIA roles used correctly
- [ ] Live regions announce updates
- [ ] Images have alt text
- [ ] Proper heading hierarchy
- [ ] Error messages clear

### Phase 3: Testing

- [ ] axe-core: 0 violations
- [ ] Screen reader: NVDA tested
- [ ] Keyboard-only: Tab works
- [ ] Color blind: Simulator tested
- [ ] Text zoom: 200% works
- [ ] Motion: Reduced motion respected

### Phase 4: Documentation

- [ ] This guide complete
- [ ] Code comments explain a11y choices
- [ ] Developers trained
- [ ] QA has checklist
- [ ] Ongoing audits scheduled

---

## Additional Resources

### Standards & References
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
- [WebAIM Resources](https://webaim.org/)

### Tools
- [axe DevTools](https://www.deque.com/axe/devtools/)
- [WAVE Browser Extension](https://wave.webaim.org/extension/)
- [Lighthouse](https://developer.chrome.com/docs/lighthouse/)
- [NVDA Screen Reader](https://www.nvaccess.org/)

### Indonesian Resources
- [WCAG in Bahasa Indonesia](https://www.w3.org/Translations/WCAG20-id/)
- [IDX Accessibility Guidelines](https://www.idx.co.id/)

---

**Accessibility leads to better products for everyone.** 🤝

Setiap fitur yang dapat diakses oleh semua pengguna adalah kemenangan bagi inklusivitas digital Indonesia.

*Every feature accessible to all users is a victory for digital inclusivity in Indonesia.*
