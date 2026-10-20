import os
import re
from urllib.parse import quote, unquote, urlparse
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, Response, abort

app = Flask(__name__)
TIMEOUT = 20

# Configure these environment variables in Render if the site's domains change.
LANG = os.getenv("BAOZI_LANGUAGE", "cn").lower()
DOMAIN = os.getenv("BAOZI_DOMAIN", "bzmgcn.com")
CDN = os.getenv("BAOZI_CDN", "as.baozimh.com")
IMAGE_QUALITY = os.getenv("BAOZI_IMAGE_QUALITY", "/w640")
BASE_URL = f"https://{LANG}.{DOMAIN}"
ALLOWED_IMAGE_HOSTS = {
    "as.baozimh.com", "as2.baozimh.com",
    "static-tw.bzmgcn.com", "static-tw.baozimh.com",
    "static-tw.ba ozimhcn.com".replace(" ", "")
}
ALLOWED_SITE_DOMAINS = {
    "bzmgcn.com", "baozimhcn.com", "webmota.com",
    "kukuc.co", "twmanga.com", "dinnerku.com"
}
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
})

def ensure_config():
    global LANG, DOMAIN, CDN, IMAGE_QUALITY, BASE_URL
    LANG = LANG if LANG in ("cn", "tw") else "cn"
    DOMAIN = DOMAIN if DOMAIN in ALLOWED_SITE_DOMAINS else "bzmgcn.com"
    CDN = CDN if CDN in ALLOWED_IMAGE_HOSTS else "as.baozimh.com"
    if IMAGE_QUALITY not in ("", "/w640"):
        IMAGE_QUALITY = "/w640"
    BASE_URL = f"https://{LANG}.{DOMAIN}"

def upstream(path):
    ensure_config()
    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")
    response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response

def soup_for(path):
    return BeautifulSoup(upstream(path).text, "html.parser")

def text_of(node):
    return " ".join(node.stripped_strings) if node else ""

def abs_url(url):
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return BASE_URL.rstrip("/") + "/" + url.lstrip("/")

def normalize_cover(url):
    url = abs_url(url)
    if not url:
        return ""
    return re.sub(r"^https://static-tw\.[^/]+", f"https://static-tw.{DOMAIN if DOMAIN in ('bzmgcn.com','baozimhcn.com') else 'bzmgcn.com'}", url)

def cover_proxy_url(url):
    return request.host_url.rstrip("/") + "/image/proxy?url=" + quote(normalize_cover(url), safe="")

def find_comics(soup):
    results = []
    seen = set()
    for a in soup.select('a[href*="/comic/"], a[href*="/book/"], a[href*="/manga/"]'):
        href = a.get("href", "")
        title = text_of(a) or a.get("title", "")
        img = a.select_one("img")
        cover = (img.get("data-src") or img.get("data-original") or img.get("src")) if img else ""
        if not title or not href or href in seen:
            continue
        seen.add(href)
        results.append({
            "comic_id": href.rstrip("/").split("/")[-1],
            "title": title,
            "cover_url": cover_proxy_url(cover) if cover else "",
            "pages": 0,
            "_href": href
        })
    return results

@app.get("/")
def index():
    return jsonify({
        "name": "包子漫画（重制版） BandComic API",
        "status": "ok",
        "config": request.host_url.rstrip("/") + "/config"
    })

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.get("/config")
def config():
    api_url = request.host_url.rstrip("/")
    # BandComic CUSTOM_SOURCE.md expects a source-name key and path prefixes
    # that the client appends IDs/keywords/page numbers to.
    return jsonify({
        "包子漫画（重制版）": {
            "name": "包子漫画（重制版）",
            "apiUrl": api_url,
            "detailPath": "/album/",
            "photoPath": "/photo//chapter/",
            "searchPath": "/search//",
            "type": "baozi_recode"
        }
    })

@app.get("/search/<path:keyword>/<int:page>")
def search(keyword, page):
    keyword = unquote(keyword).strip()
    if not keyword:
        return jsonify({"page": page, "has_more": False, "results": []})
    # Common search route; site markup can change and may need selector updates.
    try:
        s = soup_for("/search?q=" + quote(keyword))
        results = find_comics(s)
        if not results:
            s = soup_for("/search/" + quote(keyword))
            results = find_comics(s)
        per_page = 20
        start = max(0, page - 1) * per_page
        items = results[start:start + per_page]
        for item in items:
            item.pop("_href", None)
        return jsonify({"page": page, "has_more": start + per_page < len(results), "results": items})
    except Exception as exc:
        return jsonify({"code": 502, "message": "上游搜索失败，站点结构或网络可能已变化", "detail": str(exc)[:240]}), 502

@app.get("/album/<path:item_id>")
def album(item_id):
    try:
        # IDs may be full slugs. The page is located by a common Baozi comic path.
        paths = [f"/comic/{item_id}", f"/book/{item_id}", f"/manga/{item_id}"]
        last_error = None
        page_soup = None
        for path in paths:
            try:
                page_soup = soup_for(path)
                if page_soup:
                    break
            except Exception as exc:
                last_error = exc
        if page_soup is None:
            raise last_error or RuntimeError("未找到漫画详情页")
        title_node = page_soup.select_one("h1, .comic-title, .book-title, title")
        title = text_of(title_node) or str(item_id)
        img = page_soup.select_one(".comic-cover img, .book-cover img, img")
        cover = (img.get("data-src") or img.get("data-original") or img.get("src")) if img else ""
        tags = [text_of(x) for x in page_soup.select(".tag a, .tags a, a[href*='genre']") if text_of(x)]
        chapter_links = page_soup.select("a[href*='chapter'], a[href*='/read/']")
        total_chapters = max(1, len(chapter_links))
        image_count = len(page_soup.select(".chapter-list a, .episode-list a"))
        api_url = request.host_url.rstrip("/")
        return jsonify({
            "item_id": item_id,
            "name": title,
            "page_count": image_count or 1,
            "views": "",
            "rate": "",
            "cover": cover_proxy_url(cover) if cover else "",
            "tags": tags,
            "total_chapters": total_chapters
        })
    except Exception as exc:
        return jsonify({"code": 502, "message": "获取漫画详情失败，可能需要适配当前网站页面结构", "detail": str(exc)[:240]}), 502

@app.get("/photo/<path:item_id>/chapter/<int:chapter>")
def photo_list(item_id, chapter):
    try:
        paths = [
            f"/comic/{item_id}/chapter/{chapter}",
            f"/read/{item_id}/{chapter}",
            f"/chapter/{item_id}/{chapter}",
        ]
        page_soup = None
        last_error = None
        for path in paths:
            try:
                page_soup = soup_for(path)
                if page_soup:
                    break
            except Exception as exc:
                last_error = exc
        if page_soup is None:
            raise last_error or RuntimeError("未找到章节页")
        images = []
        for img in page_soup.select("img"):
            src = img.get("data-src") or img.get("data-original") or img.get("data-lazy-src") or img.get("src")
            if not src:
                continue
            full = abs_url(src)
            host = urlparse(full).hostname or ""
            if any(token in full.lower() for token in (".jpg", ".jpeg", ".png", ".webp", "image")):
                images.append({"url": request.host_url.rstrip("/") + "/image/proxy?url=" + quote(full, safe="")})
        # Deduplicate while preserving order.
        deduped = []
        seen = set()
        for image in images:
            if image["url"] not in seen:
                seen.add(image["url"])
                deduped.append(image)
        return jsonify({"title": f"{item_id} - 第{chapter}话", "images": deduped})
    except Exception as exc:
        return jsonify({"code": 502, "message": "获取章节图片失败，可能需要适配当前网站页面结构", "detail": str(exc)[:240]}), 502

@app.get("/image/proxy")
def image_proxy():
    target = request.args.get("url", "")
    if not target:
        return jsonify({"code": 400, "message": "Missing url"}), 400
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    # Restrict proxy targets to configured Baozi domains and known image hosts.
    allowed = host in ALLOWED_IMAGE_HOSTS or any(host == d or host.endswith("." + d) for d in ALLOWED_SITE_DOMAINS)
    if parsed.scheme != "https" or not allowed:
        return jsonify({"code": 400, "message": "Image host not allowed"}), 400
    try:
        res = session.get(target, timeout=TIMEOUT, stream=False)
        res.raise_for_status()
        content_type = res.headers.get("Content-Type", "image/jpeg")
        if not content_type.startswith("image/"):
            return jsonify({"code": 502, "message": "Upstream did not return an image"}), 502
        return Response(res.content, status=200, content_type=content_type,
                        headers={"Cache-Control": "public, max-age=3600", "Content-Length": str(len(res.content))})
    except Exception as exc:
        return jsonify({"code": 502, "message": "Image request failed", "detail": str(exc)[:200]}), 502

@app.errorhandler(404)
def not_found(_):
    return jsonify({"code": 404, "message": "Not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
