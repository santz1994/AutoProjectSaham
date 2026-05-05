/**
 * SymbolSelector.jsx — Multi-asset symbol selector for Phase 8.
 * 
 * Allows users to select and monitor multiple trading pairs.
 * Displays available symbols from Binance/Bybit exchanges.
 */
import React, { useState, useEffect, useCallback } from 'react';

const DEFAULT_SELECTED_SYMBOLS = ['BTC/USDT'];

const POPULAR_SYMBOLS = {
  crypto: [
    { symbol: 'BTC/USDT', name: 'Bitcoin', category: 'Major' },
    { symbol: 'ETH/USDT', name: 'Ethereum', category: 'Major' },
    { symbol: 'BNB/USDT', name: 'Binance Coin', category: 'Major' },
    { symbol: 'SOL/USDT', name: 'Solana', category: 'Major' },
    { symbol: 'XRP/USDT', name: 'Ripple', category: 'Major' },
    { symbol: 'ADA/USDT', name: 'Cardano', category: 'Altcoin' },
    { symbol: 'DOGE/USDT', name: 'Dogecoin', category: 'Meme' },
    { symbol: 'DOT/USDT', name: 'Polkadot', category: 'Altcoin' },
    { symbol: 'AVAX/USDT', name: 'Avalanche', category: 'Altcoin' },
    { symbol: 'LINK/USDT', name: 'Chainlink', category: 'DeFi' },
    { symbol: 'MATIC/USDT', name: 'Polygon', category: 'Layer2' },
    { symbol: 'UNI/USDT', name: 'Uniswap', category: 'DeFi' },
  ],
  forex: [
    { symbol: 'EUR/USD', name: 'Euro/Dollar', category: 'Major' },
    { symbol: 'GBP/USD', name: 'Pound/Dollar', category: 'Major' },
    { symbol: 'USD/JPY', name: 'Dollar/Yen', category: 'Major' },
    { symbol: 'AUD/USD', name: 'Aussie/Dollar', category: 'Major' },
    { symbol: 'USD/CHF', name: 'Dollar/Swiss', category: 'Major' },
    { symbol: 'NZD/USD', name: 'Kiwi/Dollar', category: 'Minor' },
    { symbol: 'USD/CAD', name: 'Dollar/Loonie', category: 'Major' },
  ],
};

export default function SymbolSelector({ 
  selectedSymbols,
  onSelectionChange,
  maxSelections = 10,
  showCategories = true,
  darkMode = false 
}) {
  const resolvedSelectedSymbols = selectedSymbols ?? DEFAULT_SELECTED_SYMBOLS;
  const [activeTab, setActiveTab] = useState('crypto');
  const [searchQuery, setSearchQuery] = useState('');
  const [selected, setSelected] = useState(() => new Set(resolvedSelectedSymbols));
  const [favorites, setFavorites] = useState(() => {
    try {
      const saved = localStorage.getItem('autosaham.favorites');
      return saved ? new Set(JSON.parse(saved)) : new Set(['BTC/USDT', 'ETH/USDT']);
    } catch {
      return new Set(['BTC/USDT', 'ETH/USDT']);
    }
  });

  useEffect(() => {
    if (selectedSymbols !== undefined) {
      setSelected(new Set(selectedSymbols));
    }
  }, [selectedSymbols]);

  const toggleSymbol = useCallback((symbol) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
      } else if (next.size < maxSelections) {
        next.add(symbol);
      }
      onSelectionChange?.([...next]);
      return next;
    });
  }, [maxSelections, onSelectionChange]);

  const toggleFavorite = useCallback((symbol) => {
    setFavorites(prev => {
      const next = new Set(prev);
      if (next.has(symbol)) {
        next.delete(symbol);
      } else {
        next.add(symbol);
      }
      localStorage.setItem('autosaham.favorites', JSON.stringify([...next]));
      return next;
    });
  }, []);

  const filteredSymbols = POPULAR_SYMBOLS[activeTab]?.filter(s =>
    s.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.name.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  const categories = [...new Set(filteredSymbols.map(s => s.category))];

  return (
    <div className={`symbol-selector ${darkMode ? 'dark' : 'light'}`}>
      <div className="symbol-selector-header">
        <h3>Select Trading Pairs</h3>
        <span className="selection-count">
          {selected.size}/{maxSelections} selected
        </span>
      </div>

      {/* Tabs */}
      <div className="symbol-tabs">
        <button
          className={`tab ${activeTab === 'crypto' ? 'active' : ''}`}
          onClick={() => setActiveTab('crypto')}
        >
          Crypto
        </button>
        <button
          className={`tab ${activeTab === 'forex' ? 'active' : ''}`}
          onClick={() => setActiveTab('forex')}
        >
          Forex
        </button>
      </div>

      {/* Search */}
      <div className="symbol-search">
        <input
          type="text"
          placeholder="Search symbols..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="search-input"
        />
      </div>

      {/* Symbol List */}
      <div className="symbol-list">
        {showCategories ? (
          categories.map(category => (
            <div key={category} className="symbol-category">
              <h4 className="category-title">{category}</h4>
              {filteredSymbols
                .filter(s => s.category === category)
                .map(item => (
                  <div
                    key={item.symbol}
                    className={`symbol-item ${selected.has(item.symbol) ? 'selected' : ''}`}
                  >
                    <button
                      className="favorite-btn"
                      onClick={() => toggleFavorite(item.symbol)}
                      title={favorites.has(item.symbol) ? 'Remove from favorites' : 'Add to favorites'}
                    >
                      {favorites.has(item.symbol) ? '★' : '☆'}
                    </button>
                    <div className="symbol-info" onClick={() => toggleSymbol(item.symbol)}>
                      <span className="symbol-name">{item.symbol}</span>
                      <span className="symbol-fullname">{item.name}</span>
                    </div>
                    <div className={`symbol-checkbox ${selected.has(item.symbol) ? 'checked' : ''}`}>
                      {selected.has(item.symbol) && '✓'}
                    </div>
                  </div>
                ))}
            </div>
          ))
        ) : (
          filteredSymbols.map(item => (
            <div
              key={item.symbol}
              className={`symbol-item ${selected.has(item.symbol) ? 'selected' : ''}`}
              onClick={() => toggleSymbol(item.symbol)}
            >
              <span className="symbol-name">{item.symbol}</span>
              <span className="symbol-fullname">{item.name}</span>
              <div className={`symbol-checkbox ${selected.has(item.symbol) ? 'checked' : ''}`}>
                {selected.has(item.symbol) && '✓'}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Quick Actions */}
      <div className="symbol-actions">
        <button
          className="action-btn"
          onClick={() => {
            const topPairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'];
            setSelected(new Set(topPairs));
            onSelectionChange?.(topPairs);
          }}
        >
          Top 3
        </button>
        <button
          className="action-btn"
          onClick={() => {
            setSelected(new Set());
            onSelectionChange?.([]);
          }}
        >
          Clear All
        </button>
        <button
          className="action-btn"
          onClick={() => {
            const favs = [...favorites];
            setSelected(new Set(favs));
            onSelectionChange?.(favs);
          }}
        >
          Favorites
        </button>
      </div>
    </div>
  );
}