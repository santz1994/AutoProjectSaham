"""Fetch list of companies listed on the Indonesia Stock Exchange (IDX).

This module tries multiple methods (official IDX JSON endpoint, then a public
listing page) and returns a list of dicts with `code` and `name` keys when
possible. Functions are defensive and provide clear errors when network access
or parsing fails.
"""
from typing import List, Dict


def get_idx_listings(timeout: int = 10) -> List[Dict[str, str]]:
    """Return a list of listed companies on IDX.

    Attempts:
      1. IDX public JSON endpoint(s).
      2. Fallback: public listing page scrape to extract a count (best-effort).

    Raises RuntimeError on failure with a helpful message.
    """
    try:
        import requests
    except Exception as e:
        raise RuntimeError('requests not installed; install with `pip install requests`') from e

    headers = {'User-Agent': 'AutoSaham/1.0 (+https://github.com)'}

    candidate_urls = [
        'https://www.idx.co.id/umbraco/Surface/ListedCompany/GetListedCompanies',
        'https://www.idx.co.id/umbraco/Surface/ListedCompany/GetListedCompanies?category=1',
        'https://www.idx.co.id/umbraco/Surface/ListedCompany/GetListedCompanies?type=1',
    ]

    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
        except Exception:
            continue

        if resp.status_code != 200:
            continue

        # Try parsing JSON response
        try:
            payload = resp.json()
        except Exception:
            continue

        # payload can be a list of companies or a dict containing a list
        if isinstance(payload, list):
            out = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                code = item.get('CompanyCode') or item.get('Code') or item.get('companyCode') or item.get('code')
                name = item.get('CompanyName') or item.get('Name') or item.get('companyName') or item.get('name')
                out.append({'code': code, 'name': name})
            if out:
                    from .schemas import validate_listings

                    validate_listings(out)
                    return out

        if isinstance(payload, dict):
            # common keys that may hold lists
            for key in ('Data', 'data', 'Result', 'results', 'Items', 'ListedCompanies'):
                val = payload.get(key)
                if isinstance(val, list):
                    out = []
                    for item in val:
                        if not isinstance(item, dict):
                            continue
                        code = item.get('CompanyCode') or item.get('Code') or item.get('companyCode') or item.get('code')
                        name = item.get('CompanyName') or item.get('Name') or item.get('companyName') or item.get('name')
                        out.append({'code': code, 'name': name})
                    if out:
                        from .schemas import validate_listings

                        validate_listings(out)
                        return out

            # fallback: find any list value and try to parse
            for v in payload.values():
                if isinstance(v, list):
                    out = []
                    for item in v:
                        if isinstance(item, dict):
                            code = item.get('CompanyCode') or item.get('Code') or item.get('symbol') or item.get('code')
                            name = item.get('CompanyName') or item.get('Name') or item.get('name')
                            out.append({'code': code, 'name': name})
                    if out:
                        from .schemas import validate_listings

                        validate_listings(out)
                        return out

    # Fallback: try public listing pages and extract a numeric count (best-effort)
    fallback_pages = [
        'https://stockanalysis.com/list/indonesia-stock-exchange/',
        'https://stockanalysis.com/stocks/',
    ]

    import re

    for url in fallback_pages:
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
        except Exception:
            continue

        if resp.status_code != 200:
            continue

        # Try to find phrases like "906 Stocks" or "906 stocks"
        m = re.search(r"(\d{2,4})\s+[Ss]tocks", resp.text)
        if m:
            count = int(m.group(1))
            # return placeholder entries with None codes when exact tickers unavailable
            res = [{'code': None, 'name': None} for _ in range(count)]
            from .schemas import validate_listings

            validate_listings(res)
            return res

    raise RuntimeError('Unable to fetch IDX listings from known sources; network or parsing error')


def get_idx_count() -> int:
    """Return a best-effort count of listed companies on IDX.

    This may return an approximate number if full tickers cannot be retrieved.
    """
    try:
        items = get_idx_listings()
        return len(items)
    except Exception as e:
        raise
