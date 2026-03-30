"""News connector using NewsAPI.org (requires API key).

This is a small adapter; replace with your preferred news/data feed.
"""

def fetch_news(query, from_date=None, to_date=None, api_key=None, page=1, page_size=100):
    try:
        import requests
    except Exception as e:
        raise RuntimeError('requests not installed; install with `pip install requests`') from e

    if not api_key:
        raise RuntimeError('NEWSAPI_KEY required')

    url = 'https://newsapi.org/v2/everything'
    params = {
        'q': query,
        'from': from_date or '',
        'to': to_date or '',
        'page': page,
        'pageSize': page_size,
        'apiKey': api_key,
        'language': 'en',
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()
