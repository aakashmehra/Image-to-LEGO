"""
Analytics storage and management utilities.
Tracks site visits, country visits, and other metrics.
"""
import json
import os
from typing import List, Dict, Optional
from datetime import datetime, date
from collections import defaultdict

ANALYTICS_FILE = os.path.join(os.path.dirname(__file__), "data", "analytics.json")

def ensure_directories():
    """Ensure required directories exist."""
    os.makedirs(os.path.dirname(ANALYTICS_FILE), exist_ok=True)


def load_analytics() -> Dict:
    """Load analytics data from JSON file."""
    ensure_directories()
    if not os.path.exists(ANALYTICS_FILE):
        return {
            'visits': [],
            'daily_stats': {},
            'country_stats': {},
            'page_stats': {},
            'first_visit': datetime.now().isoformat(),
            'last_update': datetime.now().isoformat()
        }
    try:
        with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {
            'visits': [],
            'daily_stats': {},
            'country_stats': {},
            'page_stats': {},
            'first_visit': datetime.now().isoformat(),
            'last_update': datetime.now().isoformat()
        }


def save_analytics(analytics: Dict):
    """Save analytics data to JSON file."""
    ensure_directories()
    analytics['last_update'] = datetime.now().isoformat()
    with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
        json.dump(analytics, f, indent=2, ensure_ascii=False)


def record_visit(page: str = '/', country: str = 'Unknown', ip_address: str = '', user_agent: str = '', referrer: str = ''):
    """Record a site visit."""
    analytics = load_analytics()
    
    visit = {
        'timestamp': datetime.now().isoformat(),
        'date': date.today().isoformat(),
        'page': page,
        'country': country,
        'ip_address': ip_address,
        'user_agent': user_agent,
        'referrer': referrer
    }
    
    analytics['visits'].append(visit)
    
    # Update daily stats
    today = date.today().isoformat()
    if today not in analytics['daily_stats']:
        analytics['daily_stats'][today] = {'visits': 0, 'unique_visitors': 0}
    analytics['daily_stats'][today]['visits'] += 1
    
    # Update country stats
    if country not in analytics['country_stats']:
        analytics['country_stats'][country] = {'visits': 0, 'last_visit': ''}
    analytics['country_stats'][country]['visits'] += 1
    analytics['country_stats'][country]['last_visit'] = datetime.now().isoformat()
    
    # Update page stats
    if page not in analytics['page_stats']:
        analytics['page_stats'][page] = {'visits': 0}
    analytics['page_stats'][page]['visits'] += 1
    
    # Keep only last 10000 visits to prevent file from growing too large
    if len(analytics['visits']) > 10000:
        analytics['visits'] = analytics['visits'][-10000:]
    
    save_analytics(analytics)


def get_analytics_summary() -> Dict:
    """Get summary statistics."""
    analytics = load_analytics()
    
    total_visits = len(analytics.get('visits', []))
    unique_countries = len(analytics.get('country_stats', {}))
    
    # Get top countries
    country_stats = analytics.get('country_stats', {})
    top_countries = sorted(
        country_stats.items(),
        key=lambda x: x[1].get('visits', 0),
        reverse=True
    )[:10]
    
    # Get top pages
    page_stats = analytics.get('page_stats', {})
    top_pages = sorted(
        page_stats.items(),
        key=lambda x: x[1].get('visits', 0),
        reverse=True
    )[:10]
    
    # Get daily visits for last 30 days
    daily_stats = analytics.get('daily_stats', {})
    recent_days = sorted(daily_stats.items(), reverse=True)[:30]
    
    return {
        'total_visits': total_visits,
        'unique_countries': unique_countries,
        'top_countries': [{'country': k, **v} for k, v in top_countries],
        'top_pages': [{'page': k, **v} for k, v in top_pages],
        'recent_days': [{'date': k, **v} for k, v in recent_days],
        'first_visit': analytics.get('first_visit', ''),
        'last_update': analytics.get('last_update', '')
    }

