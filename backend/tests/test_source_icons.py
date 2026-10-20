from app import source_icons as icons
from test_archive import client


def test_icon_endpoint_accepts_only_catalog_and_passive_raster(client,monkeypatch):
    icons.CACHE.clear();icons.INFLIGHT.clear();calls=[]
    async def fake(url):
        calls.append(url)
        return b'\x89PNG\r\n\x1a\nfixture'
    monkeypatch.setattr(icons,'fetch_feed',fake)
    r=client.get('/api/v1/source-icons/ikon.mn')
    assert r.status_code==200 and r.headers['content-type']=='image/png'
    assert r.headers['x-content-type-options']=='nosniff'
    count=len(calls)
    assert client.get('/api/v1/source-icons/ikon.mn').status_code==200 and len(calls)==count
    assert client.get('/api/v1/source-icons/127.0.0.1').status_code==404
    assert client.get('/api/v1/source-icons/unknown-not-catalog.test').status_code==404
    assert len(calls)==count
    icons.CACHE.clear()


def test_html_and_active_svg_are_not_served_as_same_origin_icons(client,monkeypatch):
    icons.CACHE.clear();icons.INFLIGHT.clear()
    async def fake(url):return b'<svg onload="alert(1)"></svg>'
    monkeypatch.setattr(icons,'fetch_feed',fake)
    assert client.get('/api/v1/source-icons/gogo.mn').status_code==404
    assert icons.image_type(b'<html>not an icon</html>') is None
    assert icons.image_type(b'RIFF1234WEBPdata')=='image/webp'
    icons.CACHE.clear()
