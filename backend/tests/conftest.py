import os,tempfile
os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db',prefix='reader-test-')
os.environ['REDIS_URL']='redis://localhost:6379/0'
os.environ['JWT_SECRET']='test-secret-3107'
import pytest
from fastapi.testclient import TestClient
from src.config.database import Base,engine,Session
from src.models.entities import User,Segment,Outreach
from src.utils.security import hash_password
from src.main import app
MEMBERS=[('SL-001',0),('SL-002',0),('SL-003',0),('SL-004',0),('SL-005',1)]
def segment_result(members):
 return {'members':[{'id':n+1,'code':c,'cluster_id':k} for n,(c,k) in enumerate(members)],'snapshot':[]}
@pytest.fixture()
def client():
 Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   s.add(User(email=role+'@demo.local',role=role,password=hash_password('Demo123!')))
  s.add(Segment(id=1,name='11月会员阅读分群',k=2,features=['weekly_reading','completion'],state='done',result=segment_result(MEMBERS)))
  s.add(Segment(id=2,name='另一版本',k=2,features=['weekly_reading','completion'],state='done',result=segment_result([('SL-901',0)])))
  s.add(Outreach(id=1,segment_id=1,cluster_id=0,title='低频轻阅读',note='每周一次短篇精选',members=['SL-001','SL-002','SL-003','SL-004'],status='approved'))
  s.add(Outreach(id=2,segment_id=1,cluster_id=1,title='夜读专题',note='每周一次夜读专题',members=['SL-005'],status='approved'))
  s.add(Outreach(id=3,segment_id=1,cluster_id=0,title='重叠方案',note='与方案一重叠的会员',members=['SL-001','SL-002'],status='approved'))
  s.add(Outreach(id=4,segment_id=1,cluster_id=0,title='未签核草案',note='尚未签核的方案',members=['SL-001'],status='draft'))
  s.add(Outreach(id=5,segment_id=2,cluster_id=0,title='其他版本方案',note='属于另一分群版本',members=['SL-901'],status='approved'))
  s.commit()
 with TestClient(app) as c:
  c.tokens={}
  for role in ('admin','analyst','viewer'):
   r=c.post('/auth/login',json={'email':role+'@demo.local','password':'Demo123!'})
   c.tokens[role]={'Authorization':'Bearer '+r.json()['token']}
  yield c
def make_experiment(client,ids=(1,2,3),title='11月触达对照实验'):
 r=client.post('/experiments',json={'segment_id':1,'outreach_ids':list(ids),'title':title,'note':'验证触达相对留白的阅读提升'},headers=client.tokens['analyst'])
 assert r.status_code==200,r.text
 return r.json()
def arms(detail):return {m['code']:m['arm'] for m in detail['members']}
