"""Owner-managed donation details. No account is published until explicitly enabled."""
import re
from pydantic import BaseModel,Field,model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from .models import SystemState,AuditLog,now

KEY='public:donation'
DEFAULT={'enabled':False,'title':'Нээлттэй мэдээллийн хяналтыг дэмжих','description':'Эх сурвалжтай, хараат бус мэдээллийн хяналтын хөгжүүлэлтийг сайн дураар дэмжих боломжтой.','bank_name':'','account_holder':'','account_number':'','currency':'MNT','transfer_note':'OpenWatch дэмжлэг','revision':0}

class DonationInput(BaseModel):
    enabled:bool=False
    title:str=Field(min_length=1,max_length=100)
    description:str=Field(default='',max_length=600)
    bank_name:str=Field(default='',max_length=100)
    account_holder:str=Field(default='',max_length=160)
    account_number:str=Field(default='',max_length=40)
    currency:str=Field(default='MNT',pattern='^(MNT|USD|EUR)$')
    transfer_note:str=Field(default='',max_length=100)
    revision:int=Field(ge=0)
    confirmed:bool=False
    @model_validator(mode='after')
    def valid_account(self):
        for field in ('title','description','bank_name','account_holder','account_number','transfer_note'):setattr(self,field,getattr(self,field).strip())
        if not self.title:raise ValueError('Гарчиг хоосон байж болохгүй.')
        compact=re.sub(r'[\s-]','',self.account_number)
        if self.account_number and not re.fullmatch(r'[A-Za-z0-9]{3,34}',compact):raise ValueError('Данс/IBAN нь 3–34 үсэг, цифрээс бүрдэнэ.')
        if self.enabled and not (self.title and self.bank_name and self.account_holder and self.account_number and self.confirmed):raise ValueError('Нийтлэхийн өмнө банк, данс, хүлээн авагч болон шалгасан баталгааг бөглөнө үү.')
        return self

def read_donation(db,private=False):
    row=db.get(SystemState,KEY)
    data={**DEFAULT,**(row.value if row else {})}
    if not private and not data['enabled']:return {'enabled':False}
    return {**data,'updated_at':row.updated_at if row else None}

def save_donation(db,data):
    row=db.scalar(select(SystemState).where(SystemState.name==KEY).with_for_update())
    revision=row.value.get('revision',0) if row else 0
    if data.revision!=revision:raise HTTPException(409,'Тохиргоо өөрчлөгдсөн. Дахин ачаалаад хадгална уу.')
    values=data.model_dump(exclude={'confirmed'});values['revision']=revision+1
    if row:row.value=values;row.updated_at=now()
    else:db.add(SystemState(name=KEY,value=values))
    db.add(AuditLog(action='donation.update',detail=f'revision={revision+1}; enabled={data.enabled}'))
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Тохиргоог өөр админ хадгалсан. Дахин ачаална уу.')
    return read_donation(db,True)
