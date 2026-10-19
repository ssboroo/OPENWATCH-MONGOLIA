import json,logging
from datetime import datetime,timezone
class JsonFormatter(logging.Formatter):
    def format(self,record):
        data={'timestamp':datetime.now(timezone.utc).isoformat(),'level':record.levelname,'logger':record.name,'message':record.getMessage()}
        if record.exc_info:data['exception']=self.formatException(record.exc_info)
        return json.dumps(data,ensure_ascii=False)
