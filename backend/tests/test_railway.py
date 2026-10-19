import pytest
from app.config import Settings

@pytest.mark.parametrize('prefix',['postgres://','postgresql://','postgresql+psycopg://'])
def test_railway_database_driver(prefix):
    url=prefix+'user:percent%40encoded@postgres.railway.internal:5432/db?sslmode=require'
    assert Settings(database_url=url,_env_file=None).database_url=='postgresql+psycopg://user:percent%40encoded@postgres.railway.internal:5432/db?sslmode=require'

def test_container_port_and_bind(monkeypatch):
    from app import serve
    calls=[]
    monkeypatch.setenv('PORT','9137');monkeypatch.setenv('BIND_HOST','::')
    monkeypatch.setattr(serve.uvicorn,'run',lambda *a,**kw:calls.append((a,kw)))
    serve.main()
    assert calls[0][1]['port']==9137 and calls[0][1]['host']=='::'
    monkeypatch.setenv('PORT','65536')
    with pytest.raises(ValueError):serve.main()
