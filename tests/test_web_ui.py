"""Automated tests for the PaperBanana Web UI.

Tests the backend endpoints, image serving, SSE format,
and validates the frontend HTML/JS for correctness.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  -- {detail}")


def fetch(path):
    url = BASE + path
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}


def fetch_post(path, body_dict, extra_headers=None):
    url = BASE + path
    payload = json.dumps(body_dict).encode()
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}


def find_run_with_images():
    """Find the most recent run directory that has iteration images."""
    outputs = Path("outputs")
    if not outputs.exists():
        return None
    for run_dir in sorted(outputs.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        images = list(run_dir.glob("diagram_iter_*.png"))
        if images:
            return run_dir
    return None


def test_server_reachable():
    print("\n[1] Server reachability")
    status, body, _ = fetch("/api/health")
    check("Health endpoint returns 200", status == 200)
    data = json.loads(body)
    check("Health returns ok=true", data.get("ok") is True)


def test_homepage():
    print("\n[2] Homepage")
    status, body, headers = fetch("/")
    html = body.decode("utf-8")
    check("Homepage returns 200", status == 200)
    check("Content-type is HTML", "text/html" in headers.get("content-type", ""))
    check("Contains PaperBanana title", "PaperBanana" in html)
    check("Contains API key input", 'id="apikeyInput"' in html)
    check("Contains generate button", 'id="generateBtn"' in html)
    check("Contains iteration grid", 'id="iterGrid"' in html)

    # Validate frontend JS uses image_url (not image_data)
    check(
        "Frontend JS uses data.image_url",
        "data.image_url" in html,
        "Frontend should reference data.image_url from SSE events",
    )
    check(
        "Frontend JS does NOT use data.image_data",
        "data.image_data" not in html,
        "Old base64 approach should be fully removed",
    )

    # Check img src uses image_url variable
    check(
        "img src uses escapeHtml(imgUrl)",
        "escapeHtml(imgUrl)" in html,
        "Image source should be set from the URL variable",
    )

    # Check download link uses href with image URL
    check(
        "Download link uses href with image URL",
        'href="' in html and "download=" in html,
        "Download should use <a href=URL download=filename>",
    )

    return html


def test_image_serving():
    print("\n[3] Image serving endpoint")
    run_dir = find_run_with_images()
    if not run_dir:
        check("Found run directory with images", False, "No run with diagram_iter_*.png found in outputs/")
        return

    outputs = Path("outputs")
    images = sorted(run_dir.glob("diagram_iter_*.png"))
    check(f"Found run with {len(images)} iteration images", len(images) > 0)

    for img in images:
        rel = img.relative_to(outputs)
        url = f"/api/images/{rel}"
        status, body, headers = fetch(url)
        size = len(body)
        check(
            f"  {img.name} serves OK ({size:,} bytes)",
            status == 200 and size > 10000,
            f"status={status}, size={size}",
        )
        check(
            f"  {img.name} content-type is image/png",
            "image/png" in headers.get("content-type", ""),
            headers.get("content-type", ""),
        )

    # Test 404 for non-existent image
    status, _, _ = fetch("/api/images/nonexistent/fake.png")
    check("Non-existent image returns 404", status == 404)


def test_favicon():
    print("\n[4] Favicon")
    status, body, headers = fetch("/favicon.png")
    check("Favicon returns 200", status == 200)
    check("Favicon is PNG", "image/png" in headers.get("content-type", ""))
    check("Favicon has data", len(body) > 100)


def test_api_generate_endpoint():
    print("\n[5] Generate endpoint")
    # We avoid sending a real POST because it triggers an expensive pipeline run
    # when GOOGLE_API_KEY is set in .env. Instead, verify the endpoint exists
    # by checking that it rejects wrong methods and bad payloads.
    status, _, _ = fetch("/api/generate")  # GET instead of POST
    check("Generate rejects GET (405 or 422)", status in (405, 422), f"Got {status}")

    # Verify OpenAPI docs list the endpoint
    status, body, _ = fetch("/openapi.json")
    check("OpenAPI schema available", status == 200)
    if status == 200:
        schema = json.loads(body)
        check("/api/generate in OpenAPI paths", "/api/generate" in schema.get("paths", {}))


def test_backend_image_url_logic():
    print("\n[6] Backend _to_image_url logic")
    sys.path.insert(0, str(Path.cwd()))
    from web.app import _to_image_url

    run_dir = find_run_with_images()
    if not run_dir:
        check("Found run for URL logic test", False)
        return

    images = sorted(run_dir.glob("diagram_iter_*.png"))
    for img in images:
        # Test with relative path (as pipeline produces)
        rel_path = str(img)
        url = _to_image_url(rel_path)
        check(
            f"  _to_image_url('{Path(rel_path).name}') returns URL",
            url is not None and url.startswith("/api/images/"),
            f"Got: {url}",
        )
        # Verify the URL would resolve to the right file
        if url:
            expected_file = Path("outputs") / url.replace("/api/images/", "")
            check(
                f"  URL resolves to existing file",
                expected_file.exists(),
                f"{expected_file} exists={expected_file.exists()}",
            )

    # Test with non-existent path
    url = _to_image_url("outputs/nonexistent/fake.png")
    check("_to_image_url returns None for missing file", url is None)


def test_sse_format():
    print("\n[7] SSE event format validation")
    sys.path.insert(0, str(Path.cwd()))
    from web.app import _sse

    event = _sse("iteration", {
        "iteration": 1,
        "image_url": "/api/images/run_test/diagram_iter_1.png",
        "description": "Test description",
        "critique": None,
    })

    check("SSE starts with 'event: '", event.startswith("event: iteration\n"))
    check("SSE has 'data: ' line", "\ndata: " in event)
    check("SSE ends with double newline", event.endswith("\n\n"))

    for line in event.strip().split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            check("SSE data has image_url field", "image_url" in data)
            check("SSE data image_url is a URL string", data["image_url"].startswith("/api/images/"))
            check("SSE data does NOT have image_data", "image_data" not in data, "base64 approach removed")
            payload_size = len(line)
            check(
                f"SSE payload is small ({payload_size} bytes)",
                payload_size < 5000,
                f"Payload was {payload_size} bytes — should be <5KB, not MB",
            )


def test_frontend_sse_parser(html):
    print("\n[8] Frontend SSE parser validation")
    check("Parser splits on \\n\\n boundary", "buffer.indexOf('\\n\\n')" in html)
    check("Parser reads 'event: ' prefix", "startsWith('event: ')" in html)
    check("Parser reads 'data: ' prefix", "startsWith('data: ')" in html)
    check("handleEvent dispatches 'iteration'", "'iteration'" in html and "addIterationCard" in html)


def test_end_to_end_image_flow():
    """Test the complete flow: image exists -> URL generated -> served via endpoint."""
    print("\n[9] End-to-end image flow")
    sys.path.insert(0, str(Path.cwd()))
    from web.app import _to_image_url

    run_dir = find_run_with_images()
    if not run_dir:
        check("Found run for E2E test", False)
        return

    img = sorted(run_dir.glob("diagram_iter_*.png"))[0]
    rel_path = str(img)

    # Step 1: _to_image_url generates correct URL
    url = _to_image_url(rel_path)
    check("Step 1: _to_image_url returns a URL", url is not None)

    if not url:
        return

    # Step 2: URL is fetchable from the server
    status, body, headers = fetch(url)
    check(f"Step 2: GET {url} returns 200", status == 200, f"Got {status}")
    check("Step 3: Response is a PNG image", "image/png" in headers.get("content-type", ""))
    check(f"Step 4: Image has data ({len(body):,} bytes)", len(body) > 10000)

    # Step 5: Image data matches the original file
    original = img.read_bytes()
    check("Step 5: Served bytes match original file", body == original, f"Served {len(body)} vs original {len(original)}")


def main():
    print("=" * 60)
    print("PaperBanana Web UI — Automated Test Suite")
    print("=" * 60)

    try:
        urllib.request.urlopen(BASE + "/api/health", timeout=3)
    except Exception:
        print(f"\nERROR: Server not running at {BASE}")
        print("Start it with: python -m uvicorn web.app:app --port 8000")
        sys.exit(1)

    test_server_reachable()
    html = test_homepage()
    test_image_serving()
    test_favicon()
    test_api_generate_endpoint()
    test_backend_image_url_logic()
    test_sse_format()
    test_frontend_sse_parser(html)
    test_end_to_end_image_flow()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED — see details above")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
