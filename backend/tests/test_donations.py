from sqlalchemy import select
from app.config import settings
from app.models import AuditLog,SystemState
from test_archive import client,db


def auth(monkeypatch):
    monkeypatch.setattr(settings,'admin_token','donation-test-only-'+'x'*32)
    return {'Authorization':'Bearer '+settings.admin_token}


def draft(revision=0,enabled=False):
    return {'enabled':enabled,'title':'[DEMO] Test support','description':'Isolated test fixture','bank_name':'[DEMO] Test bank','account_holder':'[DEMO] Test holder','account_number':'1234567890','currency':'MNT','transfer_note':'[DEMO] fixture','revision':revision,'confirmed':False}


def test_donation_is_private_until_enabled_and_unauthorized_edits_rejected(client,db,monkeypatch):
    assert client.get('/api/v1/donation').json()=={'enabled':False}
    assert client.get('/api/v1/admin/donation').status_code==401
    assert client.put('/api/v1/admin/donation',json=draft()).status_code==401
    h=auth(monkeypatch)
    r=client.put('/api/v1/admin/donation',json=draft(),headers=h)
    assert r.status_code==200 and r.json()['revision']==1
    assert r.headers['cache-control']=='no-store'
    assert client.get('/api/v1/donation').json()=={'enabled':False}
    assert client.get('/api/v1/admin/donation',headers=h).json()['account_number']=='1234567890'
    assert db.get(SystemState,'public:donation').value['revision']==1


def test_donation_publish_requires_confirmed_complete_data_and_version(client,db,monkeypatch):
    h=auth(monkeypatch);data=draft(enabled=True)
    assert client.put('/api/v1/admin/donation',headers=h,json=data).status_code==422
    data['confirmed']=True;data['account_holder']=''
    assert client.put('/api/v1/admin/donation',headers=h,json=data).status_code==422
    data['account_holder']='[DEMO] Test holder'
    r=client.put('/api/v1/admin/donation',headers=h,json=data)
    assert r.status_code==200 and r.json()['enabled'] is True
    public=client.get('/api/v1/donation').json()
    assert public['account_number']==data['account_number'] and 'confirmed' not in public
    assert client.put('/api/v1/admin/donation',headers=h,json=data).status_code==409
    disabled=draft(revision=1)
    assert client.put('/api/v1/admin/donation',headers=h,json=disabled).status_code==200
    assert client.get('/api/v1/donation').json()=={'enabled':False}
    assert len(list(db.scalars(select(AuditLog).where(AuditLog.action=='donation.update'))))==2


def test_donation_account_and_blank_title_validation(client,monkeypatch):
    h=auth(monkeypatch)
    bad=draft();bad['account_number']='https://bad.test/account'
    assert client.put('/api/v1/admin/donation',headers=h,json=bad).status_code==422
    bad=draft();bad['title']='   '
    assert client.put('/api/v1/admin/donation',headers=h,json=bad).status_code==422
