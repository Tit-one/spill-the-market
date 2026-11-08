import base64
import importlib.util
import io

import httpx
import pytest

from spill_market.page_models import PageAuditSpec, PageVariantInput, ScreenshotInput


def module():
    assert importlib.util.find_spec("spill_market.page_capture"), "page capture subsystem is missing"
    from spill_market import page_capture
    return page_capture


def image_payload(format="PNG", size=(320, 180), *, metadata=False):
    from PIL import Image
    image = Image.new("RGB", size, "#2266dd")
    stream = io.BytesIO()
    options = {}
    if metadata:
        exif = Image.Exif()
        exif[270] = "private camera description"
        options["exif"] = exif
    image.save(stream, format=format, **options)
    return base64.b64encode(stream.getvalue()).decode()


async def test_screenshot_import_normalizes_strips_metadata_and_sorts_sections(tmp_path):
    capture = module()
    from PIL import Image
    spec = PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=[
        ScreenshotInput(name="later", data_base64=image_payload("JPEG", metadata=True), scroll_y=180),
        ScreenshotInput(name="first", data_base64=image_payload("PNG")),
    ])], viewports=["desktop"], max_sections=2)
    snapshots = await capture.capture_pages(spec, tmp_path)
    assert [s.scroll_y for s in snapshots] == [0, 180]
    assert [s.section_index for s in snapshots] == [0, 1]
    assert all(s.provenance == "screenshot_import" and not s.dom and s.content_hash for s in snapshots)
    for snapshot in snapshots:
        path = tmp_path / f"{snapshot.id}.jpg"
        with Image.open(path) as image:
            assert image.format == "JPEG" and image.size == (320, 180)
            assert not image.getexif() and not image.info.get("icc_profile")
        assert snapshot.image_url == ""
        assert str(tmp_path) not in snapshot.model_dump_json()


@pytest.mark.parametrize("payload", ["not base64!", base64.b64encode(b"not an image").decode()])
async def test_invalid_images_fail_actionably_without_partial_assets(tmp_path, payload):
    capture = module()
    spec = PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=[
        ScreenshotInput(data_base64=payload)])])
    with pytest.raises(ValueError, match="image|base64"):
        await capture.capture_pages(spec, tmp_path)
    assert not list(tmp_path.glob("*.jpg"))


async def test_import_rejects_unsupported_format_and_oversize_dimensions(tmp_path):
    capture = module()
    for payload in [image_payload("GIF"), image_payload(size=(4001, 1)), image_payload(size=(3000, 9000))]:
        spec = PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=[
            ScreenshotInput(data_base64=payload)])])
        with pytest.raises(ValueError, match="format|dimension|pixel"):
            await capture.capture_pages(spec, tmp_path)


async def test_capture_cancel_preserves_committed_imports_and_progress(tmp_path):
    capture = module()
    progress = []
    spec = PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=[
        ScreenshotInput(data_base64=image_payload(), scroll_y=i * 180) for i in range(3)])],
        viewports=["desktop"], max_sections=3)
    with pytest.raises(capture.PageCaptureCancelled):
        await capture.capture_pages(spec, tmp_path, on_progress=progress.append,
                                    cancel_check=lambda: bool(progress))
    assert len(list(tmp_path.glob("*.jpg"))) == 1
    assert progress[0]["snapshot_id"]


async def test_public_fetch_pins_validated_ip_and_revalidates_redirect(monkeypatch):
    capture = module()
    requests, resolutions = [], []
    async def validated(url):
        resolutions.append(url)
        if "private" in url:
            raise ValueError("private destination blocked")
        return url, ["93.184.216.34"]
    monkeypatch.setattr(capture, "validate_public_url", validated)
    def respond(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "http://private.invalid/secret"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        fetcher = capture.PublicResourceFetcher(client=client)
        with pytest.raises(ValueError, match="private"):
            await fetcher.fetch("https://example.com/page")
    assert len(requests) == 1 and len(resolutions) == 2
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["host"] == "example.com"
    assert requests[0].extensions["sni_hostname"] == "example.com"
    assert "cookie" not in requests[0].headers


async def test_resource_limits_are_stream_bounded_and_no_cookie_replay(monkeypatch):
    capture = module()
    async def validated(url):
        return url, ["93.184.216.34"]
    monkeypatch.setattr(capture, "validate_public_url", validated)
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=b"x" * 100, headers={"content-type": "image/png", "set-cookie": "id=secret"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        fetcher = capture.PublicResourceFetcher(client=client, max_requests=2, max_resource_bytes=100,
                                                max_total_bytes=200)
        await fetcher.fetch("https://example.com/one")
        await fetcher.fetch("https://example.com/two")
        with pytest.raises(ValueError, match="request"):
            await fetcher.fetch("https://example.com/three")
    assert all("cookie" not in r.headers for r in seen)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError, match="byte|large"):
            await capture.PublicResourceFetcher(client=client, max_resource_bytes=30).fetch("https://example.com/one")


async def test_html_browser_capture_is_offline_clipped_and_truncation_is_disclosed(tmp_path, monkeypatch):
    capture = module()
    if not capture.capture_available()["available"]:
        pytest.skip("Chromium not installed; separate actionable-error regression covers availability")
    def no_network(*args, **kwargs):
        raise AssertionError("HTML capture attempted a network fetch")
    monkeypatch.setattr(capture.PublicResourceFetcher, "fetch", no_network)
    html = '<html><body style="margin:0"><h1>Visible title</h1><script>document.body.innerHTML="EXECUTED"</script>' \
           '<div style="opacity:0"><p>HIDDEN_UNSEEN</p></div><img src="http://127.0.0.1/private">' \
           '<div style="height:2500px">Long section</div><p>Later terms</p></body></html>'
    spec = PageAuditSpec(variants=[PageVariantInput(source="html", html=html)],
                         viewports=["desktop", "mobile"], max_sections=2)
    snapshots = await capture.capture_pages(spec, tmp_path)
    assert len(snapshots) == 4
    assert [(s.viewport, s.width, s.height) for s in snapshots] == [
        ("desktop", 1440, 900), ("desktop", 1440, 900), ("mobile", 390, 844), ("mobile", 390, 844)]
    assert any("truncat" in warning.lower() for s in snapshots for warning in s.warnings)
    assert any("block" in warning.lower() or "missing" in warning.lower() for s in snapshots for warning in s.warnings)
    assert "Visible title" in " ".join(e.text for e in snapshots[0].dom)
    assert "EXECUTED" not in " ".join(e.text for s in snapshots for e in s.dom)
    assert "HIDDEN_UNSEEN" not in " ".join(e.text for s in snapshots for e in s.dom)
    assert snapshots[0].dom and snapshots[2].dom
    for snapshot in snapshots:
        assert snapshot.provenance == "html_render"
        for element in snapshot.dom:
            assert 0 <= element.box.x < snapshot.width and 0 <= element.box.y < snapshot.height
            assert element.box.x + element.box.width <= snapshot.width + .01
            assert element.box.y + element.box.height <= snapshot.height + .01


async def test_demo_variants_have_distinct_actual_browser_content(tmp_path):
    capture = module()
    if not capture.capture_available()["available"]:
        pytest.skip("Chromium not installed")
    spec = PageAuditSpec(variants=[PageVariantInput(id="A"), PageVariantInput(id="B")],
                         viewports=["desktop"], max_sections=1)
    snapshots = await capture.capture_pages(spec, tmp_path)
    assert len(snapshots) == 2
    assert snapshots[0].content_hash != snapshots[1].content_hash
    assert all(s.provenance == "demo" for s in snapshots)
    assert any("fiction" in w.lower() for s in snapshots for w in s.warnings)


async def test_missing_chromium_is_an_actionable_value_error(tmp_path, monkeypatch):
    capture = module()
    monkeypatch.setattr(capture, "capture_available", lambda: {"available": False, "reason": "Missing Chromium"})
    with pytest.raises(ValueError, match="playwright install chromium"):
        await capture.capture_pages(PageAuditSpec(), tmp_path)


async def test_public_url_browser_resources_are_pinned_and_private_assets_blocked(tmp_path, monkeypatch):
    capture = module()
    if not capture.capture_available()["available"]:
        pytest.skip("Chromium not installed")
    real_validate, real_fetcher = capture.validate_public_url, capture.PublicResourceFetcher
    async def validated(url):
        if "127.0.0.1" in url:
            return await real_validate(url)
        return url, ["93.184.216.34"]
    monkeypatch.setattr(capture, "validate_public_url", validated)
    seen = []
    def respond(request):
        seen.append(request)
        if request.headers["host"] == "example.com":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=
                '<h1>Public static evidence</h1><link rel="stylesheet" href="https://assets.example.com/style.css">'
                '<img src="http://127.0.0.1/private"><link rel="preconnect" href="http://127.0.0.1/">'
                '<script>fetch("http://127.0.0.1/secret")</script>')
        return httpx.Response(200, headers={"content-type": "text/css"}, text="h1{color:#123456}")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(capture, "PublicResourceFetcher", lambda **kwargs: real_fetcher(client=client, **kwargs))
        snapshots = await capture.capture_pages(PageAuditSpec(variants=[PageVariantInput(source="url",
            url="https://example.com/")], viewports=["desktop"], max_sections=1), tmp_path)
    assert len(seen) == 2
    assert all(request.url.host == "93.184.216.34" for request in seen)
    assert snapshots[0].provenance == "public_url"
    assert any("blocked" in note.lower() for note in snapshots[0].warnings)
    assert capture.STATIC_WARNING in snapshots[0].warnings
    assert "Public static evidence" in " ".join(e.text for e in snapshots[0].dom)


async def test_import_requires_a_selected_viewport_and_discloses_missing_views(tmp_path):
    capture = module()
    image = ScreenshotInput(data_base64=image_payload(), viewport="desktop")
    with pytest.raises(ValueError, match="viewport"):
        await capture.capture_pages(PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=[image])],
                                      viewports=["mobile"]), tmp_path)
    snapshots = await capture.capture_pages(PageAuditSpec(variants=[PageVariantInput(source="screenshots",
        screenshots=[image])], viewports=["desktop", "mobile"]), tmp_path)
    assert any("mobile" in warning and "missing" in warning.lower() for warning in snapshots[0].warnings)


async def test_tall_mobile_import_is_cropped_before_progressive_exposure(tmp_path):
    capture = module()
    from PIL import Image, ImageDraw
    source = Image.new("RGB", (390, 3000), (20, 60, 200))
    ImageDraw.Draw(source).rectangle((0, 2600, 389, 2999), fill=(250, 20, 20))
    payload = io.BytesIO()
    source.save(payload, format="PNG")
    spec = PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=[ScreenshotInput(
        data_base64=base64.b64encode(payload.getvalue()).decode(), viewport="mobile")])],
        viewports=["mobile"], max_sections=6)
    snapshots = await capture.capture_pages(spec, tmp_path)
    assert [s.height for s in snapshots] == [844, 844, 844, 468]
    assert [s.scroll_y for s in snapshots] == [0, 844, 1688, 2532]
    assert [s.section_index for s in snapshots] == [0, 1, 2, 3]
    assert all(s.width == 390 and s.page_height == 3000 and not s.dom for s in snapshots)
    with Image.open(tmp_path / f"{snapshots[0].id}.jpg") as first:
        assert first.size == (390, 844)
        r, _, b = first.getpixel((100, 843))
        assert r < 80 and b > 150  # The below-fold red secret is absent.
    with Image.open(tmp_path / f"{snapshots[-1].id}.jpg") as last:
        r, _, b = last.getpixel((100, 200))
        assert r > 200 and b < 80
    assert any("without scaling" in warning.lower() for warning in snapshots[0].warnings)
    limited = await capture.capture_pages(spec.model_copy(update={"max_sections": 2}), tmp_path / "limited")
    assert len(limited) == 2 and all(s.page_height == 3000 for s in limited)
    assert all(any("truncat" in warning.lower() for warning in s.warnings) for s in limited)


async def test_cropped_imports_sort_absolute_offsets_and_have_unique_ids(tmp_path):
    capture = module()
    spec = PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=[
        ScreenshotInput(data_base64=image_payload(size=(510, 1800)), viewport="desktop", scroll_y=100),
        ScreenshotInput(data_base64=image_payload(size=(510, 900)), viewport="desktop", scroll_y=500),
    ])], viewports=["desktop"], max_sections=6)
    snapshots = await capture.capture_pages(spec, tmp_path)
    assert [s.scroll_y for s in snapshots] == [100, 500, 1000]
    assert [s.section_index for s in snapshots] == [0, 1, 2]
    assert all(s.width == 510 and s.height == 900 and s.page_height == 1900 for s in snapshots)
    assert len({s.id for s in snapshots}) == 3
