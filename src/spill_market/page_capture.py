"""Isolated, bounded static page capture; no personal browser profile or paid calls.

Chromium never fetches network resources directly. URL assets are supplied by a
public-IP-pinned HTTP fetcher; imported HTML and the fictional demo are offline.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import inspect
import io
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, UnidentifiedImageError

from .page_models import PageAuditSpec, PageSnapshot, VisibleElement
from .research import validate_public_url
from .simulation import SimulationCancelled

VIEWPORTS = {"desktop": {"width": 1440, "height": 900}, "mobile": {"width": 390, "height": 844}}
MAX_PIXELS = 24_000_000
CAPTURE_TIMEOUT_SECONDS = 90
STATIC_WARNING = "Scripts disabled; dynamic content may be missing; import screenshots for dynamic pages."


class PageCaptureCancelled(SimulationCancelled):
    """Capture stopped between committed snapshots or bounded HTTP chunks."""


def _check_cancel(cancel_check):
    if cancel_check and cancel_check():
        raise PageCaptureCancelled("Page capture cancelled; completed local snapshots are preserved")


def capture_available() -> dict:
    def probe():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).is_file()
    try:
        # The public sync API runs in an independent thread, including when this
        # capability check is called by an async HTTP handler or capture worker.
        with ThreadPoolExecutor(max_workers=1) as executor:
            available = executor.submit(probe).result(timeout=10)
        return {"available": available,
                "reason": "Chromium available" if available else
                "Chromium is missing. Run: uv run playwright install chromium"}
    except Exception as exc:
        return {"available": False, "reason":
                f"Playwright/Chromium unavailable ({type(exc).__name__}). Run: uv run playwright install chromium"}


class PublicResourceFetcher:
    """Validate every redirect and connect only to the validated IP (original SNI).

    Injected clients use the same pinned URL, enabling transport-level tests.
    No caller/browser cookies, credentials, proxy environment or headers enter.
    """

    def __init__(self, *, client=None, max_requests=40, max_resource_bytes=2_000_000,
                 max_total_bytes=12_000_000, deadline_seconds=40, cancel_check=None):
        self.client = client
        self.max_requests, self.max_resource_bytes = max_requests, max_resource_bytes
        self.max_total_bytes, self.deadline_seconds = max_total_bytes, deadline_seconds
        self.cancel_check = cancel_check
        self.requests, self.bytes = 0, 0
        self.started = time.monotonic()
        self._lock = asyncio.Lock()

    async def fetch(self, url: str) -> tuple[str, bytes, str]:
        async with self._lock:
            _check_cancel(self.cancel_check)
            remaining = self.deadline_seconds - (time.monotonic() - self.started)
            if remaining <= 0:
                raise ValueError("Public resource capture deadline exceeded")
            owned = self.client is None
            client = self.client or httpx.AsyncClient(trust_env=False, follow_redirects=False,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0))
            try:
                async with asyncio.timeout(remaining):
                    for redirect in range(6):
                        _check_cancel(self.cancel_check)
                        if self.requests >= self.max_requests:
                            raise ValueError("Public resource request limit exceeded")
                        normalized, addresses = await validate_public_url(url)
                        parsed = urlsplit(normalized)
                        target = str(httpx.URL(normalized).copy_with(host=addresses[0]))
                        self.requests += 1
                        client.cookies.clear()
                        async with client.stream("GET", target,
                            headers={"Host": parsed.netloc, "User-Agent": "SpillTheMarket/0.2 static capture",
                                     "Accept": "*/*", "Connection": "close"},
                            extensions={"sni_hostname": parsed.hostname}, follow_redirects=False,
                            timeout=min(10, remaining)) as response:
                            if response.status_code in {301, 302, 303, 307, 308}:
                                location = response.headers.get("location")
                                if not location or redirect == 5:
                                    raise ValueError("Public resource redirect limit exceeded")
                                url = urljoin(normalized, location)
                                continue
                            response.raise_for_status()
                            length = response.headers.get("content-length")
                            if length and int(length) > self.max_resource_bytes:
                                raise ValueError("Public resource byte limit exceeded")
                            body = bytearray()
                            async for chunk in response.aiter_bytes():
                                _check_cancel(self.cancel_check)
                                self.bytes += len(chunk)
                                if len(body) + len(chunk) > self.max_resource_bytes or self.bytes > self.max_total_bytes:
                                    raise ValueError("Public resource byte limit exceeded")
                                body.extend(chunk)
                            kind = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
                            return normalized, bytes(body), kind
                    raise ValueError("Public resource redirect limit exceeded")
            except TimeoutError as exc:
                raise ValueError("Public resource capture deadline exceeded") from exc
            finally:
                if owned:
                    await client.aclose()


def _dimensions(width, height):
    if width > 4000 or height > 12000 or width < 1 or height < 1:
        raise ValueError("Screenshot dimensions must be at most 4000×12000 pixels")
    if width * height > MAX_PIXELS:
        raise ValueError("Screenshot exceeds the 24-million-pixel limit")


def _normalize_image(encoded: str) -> tuple[bytes, int, int, list[str]]:
    if encoded.startswith("data:"):
        header, separator, encoded = encoded.partition(",")
        if not separator or header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
            raise ValueError("Unsupported image data URL format")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Screenshot contains invalid base64 image data") from exc
    notes = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                if probe.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Screenshot format must be PNG, JPEG or WebP")
                _dimensions(*probe.size)
                if getattr(probe, "n_frames", 1) > 1:
                    notes.append("Animated image normalized to its first frame.")
                probe.verify()
            with Image.open(io.BytesIO(data)) as opened:
                image = ImageOps.exif_transpose(opened)
                _dimensions(*image.size)
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                output = io.BytesIO()
                background.save(output, format="JPEG", quality=88, optimize=True)
                return output.getvalue(), background.width, background.height, notes
    except (UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError("Invalid or unsafe screenshot image") from exc


def _write_snapshot(directory: Path, variant_id, section, viewport, data, width, height,
                    scroll_y, page_height, provenance, dom, notes) -> PageSnapshot:
    digest = hashlib.sha256(data).hexdigest()
    identifier = f"{variant_id}-{viewport}-{section}-{digest[:16]}"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{identifier}.jpg"
    temporary = directory / f".{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return PageSnapshot(id=identifier, variant_id=variant_id, section_index=section, viewport=viewport,
                        width=width, height=height, scroll_y=scroll_y, page_height=page_height,
                        content_hash=digest, provenance=provenance, dom=dom,
                        warnings=list(dict.fromkeys(notes))[:100])


def _static_html(html: str, *, base_url: str | None = None) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "iframe", "frame", "frameset", "object", "embed", "base"]):
        element.decompose()
    for element in list(soup.find_all("meta")):
        if element.get("http-equiv"):
            element.decompose()
    for element in list(soup.find_all("link")):
        if "stylesheet" not in [str(value).lower() for value in element.get("rel", [])]:
            element.decompose()
    for element in soup.find_all(True):
        for attribute in list(element.attrs):
            if attribute.lower().startswith("on") or attribute.lower() in {"action", "formaction", "ping", "srcdoc"}:
                del element.attrs[attribute]
    if not soup.html:
        wrapper = BeautifulSoup("<!doctype html><html><head></head><body></body></html>", "html.parser")
        for child in list(soup.contents):
            wrapper.body.append(child.extract())
        soup = wrapper
    if not soup.head:
        soup.html.insert(0, soup.new_tag("head"))
    policy = soup.new_tag("meta", attrs={"http-equiv": "Content-Security-Policy", "content":
        "default-src 'none'; script-src 'none'; connect-src 'none'; object-src 'none'; frame-src 'none'; "
        "form-action 'none'; style-src 'unsafe-inline' http: https:; img-src data: http: https:; font-src data: http: https:;"})
    soup.head.insert(0, policy)
    reset = soup.new_tag("style")
    reset.string = "*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}"
    soup.head.append(reset)
    if base_url:
        soup.head.insert(1, soup.new_tag("base", href=base_url))
    return str(soup)


def _demo_html(variant_id: str) -> str:
    heading = "Make room for your next idea." if variant_id == "A" else "Finish your creative work with fewer steps."
    price = "€29 / month" if variant_id == "A" else "€290 / year · €24.17 per month"
    terms = "Cancel any time. Trial requires a card." if variant_id == "A" else "14-day trial. No card required. Export your work any time."
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>body{{margin:0;background:#f5f2e9;color:#15293b;font:20px Arial,sans-serif}}header{{padding:24px 6%;border-bottom:1px solid #9aa6ad}}
    section{{padding:70px 7%;min-height:650px;box-sizing:border-box}}h1{{font-size:clamp(40px,7vw,76px);max-width:900px}}p{{max-width:700px;line-height:1.6}}
    button{{padding:18px 28px;background:#1848ce;color:white;border:0;font-size:20px;border-radius:6px}}.terms{{background:#dbe4e6}}
    @media(max-width:600px){{section{{padding:42px 24px;min-height:800px}}h1{{font-size:44px}}}}</style></head><body>
    <header>LOOMWORK · Fictional page demonstration · Variant {variant_id}</header><section><h1>{heading}</h1>
    <p>A fictional creative workspace to organize drafts, share feedback and export finished work.</p><p>{price}</p>
    <button>Start the trial</button><p>{terms}</p></section><section class="terms"><h2>What is included?</h2>
    <p>Three workspaces, export tools and shared review links. These are invented product claims for the offline demonstration.</p>
    <h2>Clear limits</h2><p>Team seats cost extra. Internet access is required for sharing.</p></section>
    <section><h2>Before you decide</h2><p>{terms}</p><p>This page, product and pricing are entirely fictional. Buttons are not functional.</p></section></body></html>"""


_VISIBLE_DOM = r"""() => {
 const vw=innerWidth,vh=innerHeight,all=Array.from(document.body.querySelectorAll('*'));
 const elements=[]; let truncated=false, inspected=0;
 const hiddenCache=new WeakMap();
 function inheritedHidden(el){
  if(!el)return false;
  if(hiddenCache.has(el))return hiddenCache.get(el);
  const s=getComputedStyle(el);
  const hidden=s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0||s.contentVisibility==='hidden'||inheritedHidden(el.parentElement);
  hiddenCache.set(el,hidden);return hidden;
 }
 for(let index=0;index<all.length;index++){
  const el=all[index],tag=el.tagName.toLowerCase();
  if(['script','style','noscript','template'].includes(tag))continue;
  const style=getComputedStyle(el),r=el.getBoundingClientRect();
  if(inheritedHidden(el)||r.width<=0||r.height<=0||r.right<=0||r.bottom<=0||r.left>=vw||r.top>=vh)continue;
  let text='',words=0;
  for(const child of el.childNodes){
   if(child.nodeType!==Node.TEXT_NODE)continue;
   const value=child.textContent||''; const matches=value.matchAll(/\S+/g);
   for(const match of matches){
    if(++inspected>18000){truncated=true;break;}
    const range=document.createRange();range.setStart(child,match.index);range.setEnd(child,match.index+match[0].length);
    const rects=Array.from(range.getClientRects());
    if(rects.some(b=>b.right>0&&b.bottom>0&&b.left<vw&&b.top<vh)){text+=(text?' ':'')+match[0];words++;}
    if(text.length>=400)break;
   }
  }
  if(['input','textarea','select'].includes(tag))text=el.getAttribute('placeholder')||el.getAttribute('aria-label')||'';
  if(tag==='img')text=el.getAttribute('alt')||'';
  if(!text&&!['button','input','textarea','select','img'].includes(tag))continue;
  const x=Math.max(0,r.left),y=Math.max(0,r.top),right=Math.min(vw,r.right),bottom=Math.min(vh,r.bottom);
  if(right<=x||bottom<=y)continue;
  elements.push({id:'el-'+index,tag,text:text.slice(0,400),box:{x,y,width:right-x,height:bottom-y}});
  if(elements.length>=200||inspected>18000){truncated=true;break;}
 }
 return {elements,truncated};
}"""


async def capture_pages(spec: PageAuditSpec, output_dir: Path, *, on_progress=None, cancel_check=None) -> list[PageSnapshot]:
    output_dir = Path(output_dir)
    snapshots = []
    upper_bound = len(spec.variants) * len(spec.viewports) * spec.max_sections

    async def commit(snapshot):
        snapshots.append(snapshot)
        if on_progress:
            result = on_progress({"percent": min(99, round(100 * len(snapshots) / upper_bound)),
                                  "stage": "capture", "message": "Local snapshot committed",
                                  "snapshot_id": snapshot.id, "snapshot": snapshot.model_dump()})
            if inspect.isawaitable(result):
                await result

    _check_cancel(cancel_check)
    if any(v.source != "screenshots" for v in spec.variants) and not capture_available()["available"]:
        raise ValueError("Playwright Chromium is unavailable. Run: uv run playwright install chromium")
    try:
        async with asyncio.timeout(CAPTURE_TIMEOUT_SECONDS):
            for variant in spec.variants:
                _check_cancel(cancel_check)
                if variant.source == "screenshots":
                    supplied = {s.viewport for s in variant.screenshots}
                    if not supplied.intersection(spec.viewports):
                        raise ValueError("No imported screenshot matches a selected viewport")
                    missing = [f"Requested {viewport} viewport is missing from the supplied screenshots."
                               for viewport in spec.viewports if viewport not in supplied]
                    for viewport in spec.viewports:
                        selected = sorted([s for s in variant.screenshots if s.viewport == viewport], key=lambda s: s.scroll_y)
                        page_height = 1
                        crops = []
                        viewport_height = VIEWPORTS[viewport]["height"]
                        for item in selected:
                            data, width, height, notes = _normalize_image(item.data_base64)
                            page_height = max(page_height, item.scroll_y + height)
                            source_hash = hashlib.sha256(data).hexdigest()
                            for crop_y in range(0, height, viewport_height):
                                crops.append({"data": data, "width": width, "source_height": height,
                                              "source_hash": source_hash, "crop_y": crop_y,
                                              "height": min(viewport_height, height - crop_y),
                                              "scroll_y": item.scroll_y + crop_y, "warnings": notes})
                        crops.sort(key=lambda crop: crop["scroll_y"])
                        for section, crop in enumerate(crops[:spec.max_sections]):
                            _check_cancel(cancel_check)
                            data = crop["data"]
                            notes = list(crop["warnings"]) + missing + [
                                "Imported screenshot; no DOM or functional verification. Scroll offset is user-supplied; page height is inferred from supplied images."]
                            if crop["source_height"] > viewport_height:
                                with Image.open(io.BytesIO(data)) as source:
                                    image = source.crop((0, crop["crop_y"], crop["width"],
                                                         crop["crop_y"] + crop["height"]))
                                    output = io.BytesIO()
                                    image.save(output, format="JPEG", quality=88, optimize=True)
                                    data = output.getvalue()
                                notes.append(f"Imported image cropped without scaling: source {crop['width']}x{crop['source_height']}, "
                                             f"crop y={crop['crop_y']}, height={crop['height']}; "
                                             f"normalized source SHA256={crop['source_hash']}.")
                            if len(crops) > spec.max_sections:
                                notes.append("Capture coverage truncated by max_sections; later imported viewport crops were omitted.")
                            await commit(_write_snapshot(output_dir, variant.id, section, viewport, data, crop["width"],
                                crop["height"], crop["scroll_y"], page_height, "screenshot_import", [], notes))
                    continue
                from playwright.async_api import Error as BrowserError, TimeoutError as BrowserTimeout, async_playwright
                fetcher = PublicResourceFetcher(cancel_check=cancel_check)
                notes = [STATIC_WARNING,
                         "DOM boxes describe geometric viewport intersections; visual occlusion and page functionality require separate review."]
                if variant.source == "url":
                    final_url, body, content_type = await fetcher.fetch(variant.url)
                    if content_type not in {"text/html", "application/xhtml+xml"}:
                        raise ValueError("URL must return an HTML page; import a screenshot for other content")
                    html = _static_html(body.decode("utf-8", errors="replace"), base_url=final_url)
                    provenance = "public_url"
                elif variant.source == "html":
                    html, provenance = _static_html(variant.html), "html_render"
                    notes.append("Imported HTML rendered offline; external resources and active content are blocked or missing.")
                else:
                    html, provenance = _static_html(_demo_html(variant.id)), "demo"
                    notes.append("Entirely fictional local demonstration; product, claims and prices are synthetic.")
                cache = {}
                async with async_playwright() as playwright:
                    try:
                        browser = await playwright.chromium.launch(headless=True, timeout=15000,
                            proxy={"server": "http://127.0.0.1:9", "bypass": "<-loopback>"},
                            args=["--disable-background-networking", "--disable-component-update", "--disable-domain-reliability",
                                  "--host-resolver-rules=MAP * ~NOTFOUND"])
                    except BrowserError as exc:
                        raise ValueError("Chromium could not start. Run: uv run playwright install chromium") from exc
                    try:
                        for viewport in spec.viewports:
                            _check_cancel(cancel_check)
                            dimensions = VIEWPORTS[viewport]
                            context = await browser.new_context(viewport=dimensions, device_scale_factor=1,
                                java_script_enabled=False, accept_downloads=False, service_workers="block",
                                locale="en-US", timezone_id="UTC")
                            context.set_default_timeout(10000)
                            try:
                                async def resource(route):
                                    request = route.request
                                    try:
                                        _check_cancel(cancel_check)
                                        if variant.source != "url" or request.is_navigation_request() or request.resource_type not in {"image", "stylesheet", "font"}:
                                            raise ValueError("Resource or navigation blocked by static capture policy")
                                        if request.url not in cache:
                                            cache[request.url] = await fetcher.fetch(request.url)
                                        _, data, kind = cache[request.url]
                                        await route.fulfill(status=200, body=data, content_type=kind,
                                                            headers={"Access-Control-Allow-Origin": "*"})
                                    except PageCaptureCancelled:
                                        await route.abort()
                                        raise
                                    except Exception as exc:
                                        notes.append(f"Missing or blocked {request.resource_type} resource ({type(exc).__name__}); static appearance may differ.")
                                        await route.abort()
                                await context.route("**/*", resource)
                                if hasattr(context, "route_web_socket"):
                                    await context.route_web_socket("**/*", lambda socket: socket.close())
                                page = await context.new_page()
                                context.on("page", lambda popup: asyncio.create_task(popup.close()))
                                try:
                                    await page.set_content(html, wait_until="load", timeout=20000)
                                except BrowserTimeout:
                                    notes.append("Resource loading timed out; missing content may affect this static capture.")
                                actual_height = int(await page.evaluate("Math.max(document.documentElement.scrollHeight,document.body.scrollHeight,innerHeight)"))
                                page_height = min(actual_height, 200000)
                                max_scroll = max(0, page_height - dimensions["height"])
                                offsets = [0]
                                for section in range(1, spec.max_sections):
                                    offset = min(section * dimensions["height"], max_scroll)
                                    if offset <= offsets[-1]:
                                        break
                                    offsets.append(offset)
                                viewport_notes = notes.copy()
                                if offsets[-1] + dimensions["height"] < actual_height:
                                    viewport_notes.append("Capture coverage truncated by max_sections or the 200000-pixel page-height bound; later content was not captured.")
                                for section, offset in enumerate(offsets):
                                    _check_cancel(cancel_check)
                                    await page.evaluate("y=>window.scrollTo(0,y)", offset)
                                    scroll_y = int(await page.evaluate("window.scrollY"))
                                    visible = await page.evaluate(_VISIBLE_DOM)
                                    data = await page.screenshot(type="jpeg", quality=88, full_page=False, timeout=10000)
                                    section_notes = viewport_notes + notes
                                    if visible["truncated"]:
                                        section_notes.append("Visible DOM description truncated to bounded elements/text; use the image as the primary visual evidence.")
                                    await commit(_write_snapshot(output_dir, variant.id, section, viewport, data,
                                        dimensions["width"], dimensions["height"], scroll_y, page_height,
                                        provenance, [VisibleElement.model_validate(e) for e in visible["elements"]], section_notes))
                            finally:
                                await context.close()
                    finally:
                        await browser.close()
    except TimeoutError as exc:
        raise ValueError("Page capture exceeded its 90-second deadline; reduce variants or sections") from exc
    if on_progress and snapshots:
        result = on_progress({"percent": 100, "stage": "capture", "message": "Local capture complete",
                              "snapshot_id": snapshots[-1].id})
        if inspect.isawaitable(result):
            await result
    return snapshots
