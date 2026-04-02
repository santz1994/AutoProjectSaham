# Frontend Enhancement Examples

## Quick Start Examples

### 1. Using the Enhanced Button Component

```jsx
import Button from './components/Button';

// Basic button
<Button onClick={handleClick}>
  Click Me
</Button>

// Primary button with icon
<Button 
  variant="primary" 
  size="lg"
  icon={<span>🚀</span>}
  onClick={handleSubmit}
>
  Launch Trading
</Button>

// Loading state
<Button 
  variant="success" 
  loading={isProcessing}
  disabled={!canSubmit}
>
  {isProcessing ? 'Processing...' : 'Submit Order'}
</Button>

// Danger button with confirmation
<Button 
  variant="danger" 
  icon={<span>🛑</span>}
  onClick={handleEmergencyStop}
  title="Emergency stop all trading"
>
  Emergency Stop
</Button>

// Ghost button (minimal style)
<Button variant="ghost" size="sm">
  Cancel
</Button>
```

---

### 2. Using Toast Notifications

```jsx
import toast from './store/toastStore';

// Success toast
const handleSuccess = () => {
  toast.success('Trade executed successfully!');
};

// Error toast with longer duration
const handleError = () => {
  toast.error('Failed to connect to exchange', { duration: 6000 });
};

// Warning toast
const handleWarning = () => {
  toast.warning('Portfolio health score is low');
};

// Info toast
const handleInfo = () => {
  toast.info('Market is opening in 5 minutes');
};

// Loading toast (doesn't auto-dismiss)
const loadingId = toast.loading('Processing order...');

// Later, dismiss it manually
import { useToastStore } from './store/toastStore';
useToastStore.getState().removeToast(loadingId);

// Toast with action button
toast.error('Order failed', {
  duration: 8000,
  action: {
    label: 'Retry',
    onClick: () => retryOrder(),
  },
});
```

---

### 3. Using Loading Skeletons

```jsx
import {
  CardSkeleton,
  ChartSkeleton,
  TableSkeleton,
  Spinner,
  ProgressBar,
  LoadingOverlay,
} from './components/LoadingSkeletons';

// Card with loading state
function PortfolioCard() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  if (loading) {
    return <CardSkeleton />;
  }

  return <div className="card">{/* card content */}</div>;
}

// Chart with loading state
function TradingChart() {
  const [loading, setLoading] = useState(true);

  if (loading) {
    return <ChartSkeleton />;
  }

  return <div className="chart">{/* chart content */}</div>;
}

// Table with loading state
function TradeHistory() {
  const [loading, setLoading] = useState(true);

  if (loading) {
    return <TableSkeleton rows={10} columns={5} />;
  }

  return <table>{/* table content */}</table>;
}

// Inline spinner
<Button loading={isProcessing}>
  <Spinner size="sm" />
  Processing
</Button>

// Progress bar
<ProgressBar 
  progress={uploadProgress} 
  label="Uploading strategy..." 
  showPercentage={true} 
/>

// Full-screen loading overlay
{isInitializing && (
  <LoadingOverlay message="Initializing AutoSaham..." />
)}
```

---

### 4. Using Error Boundaries

```jsx
import ErrorBoundary from './components/ErrorBoundary';

// Wrap a component
function DashboardPage() {
  return (
    <ErrorBoundary>
      <Dashboard />
    </ErrorBoundary>
  );
}

// Wrap multiple sections
function App() {
  return (
    <div>
      <ErrorBoundary>
        <Navbar />
      </ErrorBoundary>

      <ErrorBoundary>
        <Sidebar />
      </ErrorBoundary>

      <ErrorBoundary>
        <MainContent />
      </ErrorBoundary>
    </div>
  );
}

// Custom fallback UI
function CustomErrorFallback({ error, onReset }) {
  return (
    <div className="custom-error">
      <h2>Oops! Something went wrong</h2>
      <p>{error.message}</p>
      <button onClick={onReset}>Try Again</button>
    </div>
  );
}

<ErrorBoundary fallback={CustomErrorFallback}>
  <YourComponent />
</ErrorBoundary>

// With callback on reset
<ErrorBoundary onReset={() => {
  // Clear state, refetch data, etc.
  console.log('Error boundary reset');
}}>
  <YourComponent />
</ErrorBoundary>

// Using HOC wrapper
import { withErrorBoundary } from './components/ErrorBoundary';

function MyComponent() {
  return <div>My Component</div>;
}

export default withErrorBoundary(MyComponent);
```

---

### 5. Keyboard Shortcuts Integration

```jsx
// The enhanced sidebar already includes these shortcuts:

// Ctrl+1 - Go to Dashboard
// Ctrl+2 - Go to Market Intelligence
// Ctrl+3 - Go to Strategies
// Ctrl+4 - Go to Trade Logs
// Ctrl+5 - Go to Settings
// Ctrl+B - Toggle Sidebar
// Ctrl+K - Open Search
// Ctrl+/ - Show Keyboard Shortcuts
// Esc - Close Modals/Dropdowns

// Add custom shortcuts in your component:
useEffect(() => {
  const handleKeyDown = (e) => {
    // Ctrl+S to save
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault();
      handleSave();
    }

    // Ctrl+E to export
    if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
      e.preventDefault();
      handleExport();
    }
  };

  document.addEventListener('keydown', handleKeyDown);
  return () => document.removeEventListener('keydown', handleKeyDown);
}, []);
```

---

### 6. Complete Page Example

```jsx
import React, { useState, useEffect } from 'react';
import Button from './components/Button';
import toast from './store/toastStore';
import { CardSkeleton, Spinner } from './components/LoadingSkeletons';
import ErrorBoundary from './components/ErrorBoundary';

function TradingStrategyPage() {
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState(null);

  // Load strategies
  useEffect(() => {
    async function loadStrategies() {
      try {
        setLoading(true);
        const response = await fetch('/api/strategies');
        const data = await response.json();
        setStrategies(data);
        toast.success('Strategies loaded');
      } catch (error) {
        toast.error('Failed to load strategies');
      } finally {
        setLoading(false);
      }
    }
    loadStrategies();
  }, []);

  // Save strategy
  const handleSave = async () => {
    try {
      setSaving(true);
      await fetch('/api/strategies', {
        method: 'POST',
        body: JSON.stringify(selectedStrategy),
      });
      toast.success('Strategy saved successfully!', {
        action: {
          label: 'View',
          onClick: () => navigate('/strategies'),
        },
      });
    } catch (error) {
      toast.error('Failed to save strategy');
    } finally {
      setSaving(false);
    }
  };

  // Delete strategy
  const handleDelete = async (id) => {
    try {
      await fetch(`/api/strategies/${id}`, { method: 'DELETE' });
      setStrategies(strategies.filter((s) => s.id !== id));
      toast.success('Strategy deleted');
    } catch (error) {
      toast.error('Failed to delete strategy');
    }
  };

  if (loading) {
    return (
      <div className="strategy-page">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="strategy-page">
        <div className="page-header">
          <h1>Trading Strategies</h1>
          <div className="actions">
            <Button variant="primary" icon={<span>➕</span>} onClick={handleNew}>
              New Strategy
            </Button>
            <Button 
              variant="success" 
              loading={saving} 
              onClick={handleSave}
              disabled={!selectedStrategy}
            >
              {saving ? 'Saving...' : 'Save Strategy'}
            </Button>
          </div>
        </div>

        <div className="strategies-grid">
          {strategies.map((strategy) => (
            <div key={strategy.id} className="strategy-card">
              <h3>{strategy.name}</h3>
              <p>{strategy.description}</p>
              <div className="card-actions">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setSelectedStrategy(strategy)}
                >
                  Edit
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => handleDelete(strategy.id)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </ErrorBoundary>
  );
}

export default TradingStrategyPage;
```

---

### 7. Form with Validation Example

```jsx
import React, { useState } from 'react';
import Button from './components/Button';
import toast from './store/toastStore';

function LoginForm() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const validate = () => {
    const newErrors = {};
    if (!username) newErrors.username = 'Username is required';
    if (!password) newErrors.password = 'Password is required';
    if (password.length < 6) newErrors.password = 'Password must be at least 6 characters';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validate()) {
      toast.error('Please fix the errors in the form');
      return;
    }

    try {
      setLoading(true);
      const response = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        throw new Error('Login failed');
      }

      toast.success('Login successful!');
      // Redirect or update state
    } catch (error) {
      toast.error('Invalid username or password', {
        action: {
          label: 'Reset Password',
          onClick: () => navigate('/reset-password'),
        },
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="login-form">
      <div className="form-group">
        <label htmlFor="username">Username</label>
        <input
          id="username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className={errors.username ? 'error' : ''}
        />
        {errors.username && <span className="error-message">{errors.username}</span>}
      </div>

      <div className="form-group">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={errors.password ? 'error' : ''}
        />
        {errors.password && <span className="error-message">{errors.password}</span>}
      </div>

      <Button
        type="submit"
        variant="primary"
        fullWidth
        loading={loading}
        icon={<span>🔐</span>}
      >
        {loading ? 'Logging in...' : 'Login'}
      </Button>
    </form>
  );
}

export default LoginForm;
```

---

## Best Practices

1. **Always wrap pages with ErrorBoundary**
2. **Show loading states for all async operations**
3. **Provide feedback with toast notifications**
4. **Use appropriate button variants for actions**
5. **Test keyboard navigation**
6. **Ensure mobile responsiveness**
7. **Add ARIA labels for accessibility**
8. **Handle errors gracefully**

---

**Need more examples?** Check the component source files for additional usage patterns and props!
