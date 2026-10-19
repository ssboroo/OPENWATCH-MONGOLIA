from .evidence import redact

def article_data(a):
    keys=['id','source_id','url','title','excerpt','text_hash','published_at','updated_at','first_seen_at','fetched_at','version','analysis_status','rights_status']
    data={k:getattr(a,k) for k in keys}
    data['title']=redact(data['title']);data['excerpt']=redact(data['excerpt'])
    return data
