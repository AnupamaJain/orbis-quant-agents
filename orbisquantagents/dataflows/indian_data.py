"""Advanced Indian Data Connectors for NSE/BSE stocks."""

import yfinance as yf
from datetime import datetime
from .stockstats_utils import yf_retry

def get_sebi_filings(ticker: str) -> str:
    """
    Retrieve recent SEBI corporate filings and announcements for an Indian stock.
    
    Args:
        ticker: Indian stock ticker (e.g., "RELIANCE.NS")
        
    Returns:
        Formatted string containing recent announcements and filings.
    """
    clean_ticker = ticker.split('.')[0] if '.' in ticker else ticker
    search_query = f"{clean_ticker} corporate announcements filings site:nseindia.com OR site:bseindia.com"
    
    try:
        search = yf_retry(lambda: yf.Search(
            query=search_query,
            news_count=10,
            enable_fuzzy_query=True
        ))
        
        if not search.news:
            return f"No recent SEBI filings or announcements found for {ticker}."
            
        filings_str = f"## Recent SEBI Filings & Announcements for {ticker}\n\n"
        for article in search.news:
            # Handle nested 'content' structure in newer yfinance versions
            content = article.get("content", article)
            title = content.get("title", "No Title")
            link = content.get("canonicalUrl", {}).get("url") or content.get("link", "")
            publisher = content.get("provider", {}).get("displayName") or content.get("publisher", "Unknown")
            
            filings_str += f"### {title}\n"
            filings_str += f"- **Source**: {publisher}\n"
            if link:
                filings_str += f"- **Document/Link**: {link}\n"
            filings_str += "\n"
            
        return filings_str
        
    except Exception as e:
        return f"Error fetching SEBI filings for {ticker}: {str(e)}"

def get_bulk_block_deals(ticker: str) -> str:
    """
    Retrieve recent Bulk and Block deals for an Indian stock.
    
    Args:
        ticker: Indian stock ticker (e.g., "RELIANCE.NS")
        
    Returns:
        Formatted string containing recent deal data.
    """
    clean_ticker = ticker.split('.')[0] if '.' in ticker else ticker
    search_query = f"{clean_ticker} bulk block deals NSE BSE"
    
    try:
        search = yf_retry(lambda: yf.Search(
            query=search_query,
            news_count=5,
            enable_fuzzy_query=True
        ))
        
        if not search.news:
            return f"No recent Bulk or Block deals found for {ticker}."
            
        deals_str = f"## Recent Bulk & Block Deals for {ticker}\n\n"
        for article in search.news:
            content = article.get("content", article)
            title = content.get("title", "No Title")
            summary = content.get("summary", "")
            link = content.get("canonicalUrl", {}).get("url") or content.get("link", "")
            
            deals_str += f"### {title}\n"
            if summary:
                deals_str += f"{summary}\n"
            if link:
                deals_str += f"- **More Info**: {link}\n"
            deals_str += "\n"
            
        return deals_str
        
    except Exception as e:
        return f"Error fetching Bulk/Block deals for {ticker}: {str(e)}"

def get_government_tenders(ticker: str) -> str:
    """
    Retrieve recent government tender wins, order announcements, and PSU-specific news.
    
    Args:
        ticker: Indian stock ticker (e.g., "SJVN.NS")
        
    Returns:
        Formatted string containing recent tender and order information.
    """
    clean_ticker = ticker.split('.')[0] if '.' in ticker else ticker
    search_query = f"{clean_ticker} government order win tender award contract PSU news"
    
    try:
        search = yf_retry(lambda: yf.Search(
            query=search_query,
            news_count=8,
            enable_fuzzy_query=True
        ))
        
        if not search.news:
            return f"No recent government tender or order information found for {ticker}."
            
        tenders_str = f"## Government Tenders & Order Wins for {ticker}\n\n"
        for article in search.news:
            content = article.get("content", article)
            title = content.get("title", "No Title")
            summary = content.get("summary", "")
            link = content.get("canonicalUrl", {}).get("url") or content.get("link", "")
            
            tenders_str += f"### {title}\n"
            if summary:
                tenders_str += f"{summary}\n"
            if link:
                tenders_str += f"- **Official Announcement/Link**: {link}\n"
            tenders_str += "\n"
            
        return tenders_str
        
    except Exception as e:
        return f"Error fetching government tenders for {ticker}: {str(e)}"
