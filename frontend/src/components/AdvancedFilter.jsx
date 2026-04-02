/**
 * Advanced Filter Component
 * Reusable filter panel for tables and lists
 */
import React, { useState } from 'react';
import Button from './Button';
import './AdvancedFilter.css';

export default function AdvancedFilter({ 
  filters, 
  onApply, 
  onReset,
  isOpen,
  onToggle 
}) {
  const [localFilters, setLocalFilters] = useState(filters);

  const handleChange = (key, value) => {
    setLocalFilters(prev => ({ ...prev, [key]: value }));
  };

  const handleApply = () => {
    onApply(localFilters);
  };

  const handleReset = () => {
    const resetFilters = Object.keys(localFilters).reduce((acc, key) => {
      acc[key] = '';
      return acc;
    }, {});
    setLocalFilters(resetFilters);
    onReset();
  };

  if (!isOpen) {
    return (
      <Button 
        variant="secondary" 
        size="sm"
        icon={<span>🔍</span>}
        onClick={onToggle}
      >
        Show Filters
      </Button>
    );
  }

  return (
    <div className="advanced-filter">
      <div className="filter-header">
        <h3>🔍 Filters</h3>
        <Button 
          variant="ghost" 
          size="sm"
          onClick={onToggle}
        >
          ✕
        </Button>
      </div>

      <div className="filter-grid">
        {Object.entries(localFilters).map(([key, value]) => (
          <div key={key} className="filter-item">
            <label>{key.charAt(0).toUpperCase() + key.slice(1).replace(/([A-Z])/g, ' $1')}</label>
            <input
              type="text"
              value={value}
              onChange={(e) => handleChange(key, e.target.value)}
              placeholder={`Filter by ${key}...`}
            />
          </div>
        ))}
      </div>

      <div className="filter-actions">
        <Button 
          variant="primary" 
          size="sm"
          onClick={handleApply}
        >
          Apply Filters
        </Button>
        <Button 
          variant="ghost" 
          size="sm"
          onClick={handleReset}
        >
          Reset All
        </Button>
      </div>
    </div>
  );
}
