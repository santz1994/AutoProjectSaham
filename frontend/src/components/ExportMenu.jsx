/**
 * Export Menu Component
 * Dropdown menu for exporting data in various formats
 */
import React, { useState } from 'react';
import Button from './Button';
import toast from '../store/toastStore';
import './ExportMenu.css';

export default function ExportMenu({ 
  data, 
  filename = 'export',
  onExport 
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleExport = async (format) => {
    setExporting(true);
    setIsOpen(false);

    try {
      if (onExport) {
        await onExport(format);
      } else {
        // Default export logic
        await exportData(format);
      }
      toast.success(`Exported as ${format.toUpperCase()} successfully!`);
    } catch (error) {
      toast.error('Export failed: ' + error.message);
    } finally {
      setExporting(false);
    }
  };

  const exportData = async (format) => {
    return new Promise((resolve) => {
      setTimeout(() => {
        console.log(`Exporting as ${format}:`, data);
        
        // Simulate file download
        if (format === 'csv') {
          downloadCSV();
        } else if (format === 'json') {
          downloadJSON();
        } else if (format === 'pdf') {
          // PDF export would use jsPDF or similar
          console.log('PDF export not yet implemented');
        }
        
        resolve();
      }, 500);
    });
  };

  const downloadCSV = () => {
    if (!data || data.length === 0) return;

    const headers = Object.keys(data[0]).join(',');
    const rows = data.map(row => Object.values(row).join(',')).join('\n');
    const csv = `${headers}\n${rows}`;
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const downloadJSON = () => {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="export-menu-container">
      <Button
        variant="secondary"
        size="sm"
        icon={<span>📥</span>}
        onClick={() => setIsOpen(!isOpen)}
        loading={exporting}
      >
        Export
      </Button>

      {isOpen && (
        <>
          <div className="export-backdrop" onClick={() => setIsOpen(false)} />
          <div className="export-menu">
            <div className="export-menu-header">
              <span>Export as</span>
            </div>
            <button 
              className="export-option"
              onClick={() => handleExport('csv')}
            >
              <span className="export-icon">📊</span>
              <div className="export-info">
                <strong>CSV</strong>
                <small>Comma-separated values</small>
              </div>
            </button>
            <button 
              className="export-option"
              onClick={() => handleExport('json')}
            >
              <span className="export-icon">📄</span>
              <div className="export-info">
                <strong>JSON</strong>
                <small>JavaScript Object Notation</small>
              </div>
            </button>
            <button 
              className="export-option"
              onClick={() => handleExport('excel')}
            >
              <span className="export-icon">📗</span>
              <div className="export-info">
                <strong>Excel</strong>
                <small>Microsoft Excel format</small>
              </div>
            </button>
            <button 
              className="export-option"
              onClick={() => handleExport('pdf')}
            >
              <span className="export-icon">📕</span>
              <div className="export-info">
                <strong>PDF</strong>
                <small>Portable Document Format</small>
              </div>
            </button>
          </div>
        </>
      )}
    </div>
  );
}
