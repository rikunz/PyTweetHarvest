import os
import json
import hashlib
import gzip
from pathlib import Path
from typing import Dict, Optional
from logging_setup import logger

class PlaywrightCache:
    """Cache system untuk menyimpan response static files dari Twitter/X.com"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_metadata_file = self.cache_dir / "cache_metadata.json"
        self.cache_metadata = self._load_metadata()
        
    def _load_metadata(self) -> Dict:
        """Load cache metadata from file"""
        if self.cache_metadata_file.exists():
            try:
                with open(self.cache_metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache metadata: {e}")
        return {}
    
    def _save_metadata(self):
        """Save cache metadata to file"""
        try:
            with open(self.cache_metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache metadata: {e}")
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def _get_cache_file_path(self, cache_key: str) -> Path:
        """Get cache file path"""
        return self.cache_dir / f"{cache_key}.cache"
    
    def should_cache_url(self, url: str, content_type: Optional[str] = None) -> bool:
        """Determine if URL should be cached"""
        not_cachable_patterns = ["video.twimg.com", "/i/videos/", ".mp4", ".mov", ".avi", ".mkv", "pbs.twimg.com", "/emoji/"]
        for pattern in not_cachable_patterns:
            if pattern in url:
                return False
        # Cache static files yang umum di Twitter/X.com
        cacheable_patterns = [
            '/responsive-web/client-web/',
            '/i/js_inst/',
            '/abs.twimg.com/',
            'twimg.com',
            'twitter.com',
            'x.com',
            '.js',
            '.css',
            '.woff2',
            '.woff',
            '.ttf',
            '.gif',
            '.ico'
        ]
        
        cacheable_content_types = [
            'application/javascript',
            'text/javascript',
            'text/css',
            'font/',
            'image/',
            'application/font'
        ]
        
        # Check URL patterns
        for pattern in cacheable_patterns:
            if pattern in url:
                logger.debug(f"URL {url} matches cacheable pattern: {pattern}")
                return True
                
        # Check content type
        if content_type:
            for ct in cacheable_content_types:
                if ct in content_type:
                    logger.debug(f"URL {url} matches cacheable content type: {ct}")
                    return True
        
        logger.debug(f"URL {url} not cacheable (content-type: {content_type})")
        return False
    
    def get_cached_response(self, url: str) -> Optional[Dict]:
        """Get cached response if exists"""
        cache_key = self._get_cache_key(url)
        
        if cache_key not in self.cache_metadata:
            return None
            
        cache_file = self._get_cache_file_path(cache_key)
        if not cache_file.exists():
            # Remove stale metadata
            del self.cache_metadata[cache_key]
            self._save_metadata()
            return None
            
        try:
            with open(cache_file, 'rb') as f:
                compressed_data = f.read()
                
            # Decompress data
            response_data = gzip.decompress(compressed_data)
            metadata = self.cache_metadata[cache_key]
            
            return {
                'body': response_data,
                'headers': metadata['headers'],
                'status': metadata['status'],
                'url': url
            }
        except Exception as e:
            logger.error(f"Failed to read cache for {url}: {e}")
            return None
    
    def cache_response(self, url: str, response_data: bytes, headers: Dict, status: int):
        """Cache response data"""
        try:
            logger.info(f"Attempting to cache: {url} ({len(response_data)} bytes)")
            
            cache_key = self._get_cache_key(url)
            cache_file = self._get_cache_file_path(cache_key)
            
            logger.debug(f"Cache file path: {cache_file}")
            
            # Compress and save response data
            compressed_data = gzip.compress(response_data)
            with open(cache_file, 'wb') as f:
                f.write(compressed_data)
            
            logger.debug(f"Compressed data written to {cache_file}")
            
            # Save metadata
            self.cache_metadata[cache_key] = {
                'url': url,
                'headers': headers,
                'status': status,
                'cached_at': str(Path(cache_file).stat().st_mtime),
                'size': len(response_data)
            }
            self._save_metadata()
            
            logger.info(f"Successfully cached response for {url} ({len(response_data)} bytes -> {len(compressed_data)} compressed)")
            
        except Exception as e:
            logger.error(f"Failed to cache response for {url}: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def clear_cache(self):
        """Clear all cached files"""
        try:
            for cache_file in self.cache_dir.glob("*.cache"):
                cache_file.unlink()
            self.cache_metadata = {}
            self._save_metadata()
            logger.info("Cache cleared successfully")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        total_files = len(self.cache_metadata)
        total_size = 0
        
        for cache_key in self.cache_metadata:
            cache_file = self._get_cache_file_path(cache_key)
            if cache_file.exists():
                total_size += cache_file.stat().st_size
        
        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'cache_dir': str(self.cache_dir)
        }


async def setup_cache_interceptor(page, cache: PlaywrightCache):
    """Setup Playwright page untuk menggunakan cache system"""
    
    logger.info("Setting up cache interceptor...")
    
    # Counter untuk tracking requests
    request_count = 0
    cached_count = 0
    
    async def handle_route(route):
        nonlocal request_count, cached_count
        request = route.request
        url = request.url
        
        request_count += 1
        logger.debug(f"[{request_count}] Intercepted request: {url[:100]}...")
        
        # Check if we should cache this URL
        should_cache = cache.should_cache_url(url)
        
        if not should_cache:
            logger.debug(f"[{request_count}] Not cacheable, continuing: {url[:100]}...")
            await route.continue_()
            return
        
        logger.info(f"[{request_count}] Cacheable URL found: {url}")
        
        # Try to get from cache first
        cached_response = cache.get_cached_response(url)
        if cached_response:
            cached_count += 1
            logger.info(f"[{request_count}] ✅ Serving from cache ({cached_count} total): {url}")
            await route.fulfill(
                status=cached_response['status'],
                headers=cached_response['headers'],
                body=cached_response['body']
            )
            return
        
        logger.info(f"[{request_count}] 📥 Fetching and caching: {url}")
        
        # If not in cache, continue with request and cache the response
        try:
            response = await route.fetch()
            body = await response.body()
            headers = response.headers
            status = response.status
            
            logger.debug(f"[{request_count}] Response status for {url}: {status}")
            
            # Cache the response
            if status == 200:  # Only cache successful responses
                cache.cache_response(url, body, headers, status)
                logger.info(f"[{request_count}] ✅ Successfully cached: {url} ({len(body)} bytes)")
            else:
                logger.debug(f"[{request_count}] Not caching {url} due to status {status}")
            
            await route.fulfill(
                status=status,
                headers=headers,
                body=body
            )
            
        except Exception as e:
            logger.error(f"[{request_count}] Failed to handle cached route for {url}: {e}")
            await route.continue_()
    
    # Setup route interceptor untuk semua requests
    await page.route("**/*", handle_route)
    logger.info("Cache interceptor setup complete - will intercept ALL requests")
