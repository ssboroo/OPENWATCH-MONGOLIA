import sys
from sqlalchemy import select,text
from .db import Session
from .models import SystemState,now
from .clustering import utc
with Session() as db:
    db.execute(text('SELECT 1'))
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        state=db.get(SystemState,'worker')
        if state is None or (now()-utc(state.updated_at)).total_seconds()>600:
            raise SystemExit(1)
