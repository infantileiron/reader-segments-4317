from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from src.main import app
from conftest import make_experiment,arms
def test_merge_dedupe_and_balanced_split(client):
 d=make_experiment(client)
 assert d['status']=='running' and d['outreach_ids']==[1,2,3]
 a=arms(d)
 assert sorted(a)==['SL-001','SL-002','SL-003','SL-004','SL-005'] # 重叠方案会员只分一次
 c0=[m for m in d['members'] if m['cluster_id']==0]
 assert sum(m['arm']=='touch' for m in c0)==2 and sum(m['arm']=='holdout' for m in c0)==2 # 按群均分
 c1=[m for m in d['members'] if m['cluster_id']==1]
 assert len(c1)==1 and c1[0]['arm']=='touch' # 单会员群留白为空
def test_retry_grouping_is_deterministic(client):
 first=make_experiment(client,title='第一次');second=make_experiment(client,title='重试')
 assert first['id']!=second['id'] and first['seed']==second['seed']
 assert arms(first)==arms(second) # 重试分组保持一致
def test_create_validations(client):
 h=client.tokens['analyst']
 assert client.post('/experiments',json={'segment_id':1,'outreach_ids':[4],'title':'含草案','note':'包含未签核方案的实验'},headers=h).status_code==409
 assert client.post('/experiments',json={'segment_id':1,'outreach_ids':[1,5],'title':'跨版本','note':'合并不同分群版本的方案'},headers=h).status_code==422
 assert client.post('/experiments',json={'segment_id':1,'outreach_ids':[99],'title':'不存在','note':'方案编号不存在的情况'},headers=h).status_code==404
 assert client.post('/experiments',json={'segment_id':1,'outreach_ids':[1],'title':'观察员','note':'观察员不能开启实验'},headers=client.tokens['viewer']).status_code==403
def test_export_only_touch_group(client):
 d=make_experiment(client)
 r=client.get('/experiments/%s/export'%d['id'],headers=client.tokens['viewer'])
 assert r.status_code==200
 body=r.json();touch={m['code'] for m in d['members'] if m['arm']=='touch'}
 assert body['arm']=='touch' and set(body['members'])==touch # 名单仅导出触达组
 assert all(m['arm']=='touch' for m in d['members'] if m['code'] in body['members'])
def test_receipts_replay_quarantine_and_report(client):
 d=make_experiment(client);a=arms(d);i=d['id'];h=client.tokens['analyst']
 touch=next(c for c in a if a[c]=='touch');holdout=next(c for c in a if a[c]=='holdout')
 batch=[{'event_id':'EV-1','code':touch},{'event_id':'EV-2','code':holdout},{'event_id':'EV-3','code':'SL-999'},{'event_id':'EV-1','code':touch}]
 r=client.post('/experiments/%s/receipts'%i,json={'receipts':batch},headers=h)
 assert r.json()=={'accepted':2,'replayed':1,'quarantined':1} # 批内重复事件只入账一次
 again=client.post('/experiments/%s/receipts'%i,json={'receipts':batch},headers=h)
 assert again.json()=={'accepted':0,'replayed':4,'quarantined':0} # 重放不重复入账，隔离记录也不重复
 d2=client.get('/experiments/%s'%i,headers=h).json()
 assert d2['receipt_count']==2 and len(d2['quarantine'])==1
 assert d2['quarantine'][0]['event_id']=='EV-3' and d2['quarantine'][0]['reason']=='会员不在实验名单'
 rows={row['cluster_id']:row for row in d2['report']['rows']}
 overall=rows[None]
 assert overall['touch']['read']==1 and overall['holdout']['read']==1
 assert overall['touch']['members']==3 and overall['holdout']['members']==2 # 分母含未阅读会员
 assert abs(overall['touch']['rate']-1/3)<1e-9 and abs(overall['holdout']['rate']-1/2)<1e-9
 assert abs(overall['diff']-(1/3-1/2))<1e-9
def test_cross_experiment_same_event_id(client):
 first=make_experiment(client,title='实验一');second=make_experiment(client,title='实验二');h=client.tokens['analyst']
 code=first['members'][0]['code']
 for i in (first['id'],second['id']):
  r=client.post('/experiments/%s/receipts'%i,json={'receipts':[{'event_id':'EV-SHARED','code':code}]},headers=h)
  assert r.json()['accepted']==1 # 同一事件编号跨实验互不影响
 assert client.get('/experiments/%s'%first['id'],headers=h).json()['receipt_count']==1
 assert client.get('/experiments/%s'%second['id'],headers=h).json()['receipt_count']==1
def test_empty_group_reports_null_not_zero(client):
 d=make_experiment(client);h=client.tokens['analyst']
 rows={row['cluster_id']:row for row in d['report']['rows']}
 assert rows[1]['holdout']['members']==0 and rows[1]['holdout']['rate'] is None # 空组不报零转化
 assert rows[1]['diff'] is None
 assert rows[1]['touch']['rate']==0.0 # 非空组无回执是真实零转化
 assert rows[None]['touch']['members']==3 and rows[None]['holdout']['members']==2
def test_archive_freezes_and_rejects(client):
 d=make_experiment(client);i=d['id'];h=client.tokens['analyst'];a=arms(d)
 touch=next(c for c in a if a[c]=='touch')
 client.post('/experiments/%s/receipts'%i,json={'receipts':[{'event_id':'EV-1','code':touch}]},headers=h)
 done=client.post('/experiments/%s/archive'%i,json={},headers=h)
 assert done.status_code==200 and done.json()['status']=='archived'
 frozen=done.json()['report'];assert frozen['live'] is False
 assert client.post('/experiments/%s/receipts'%i,json={'receipts':[{'event_id':'EV-2','code':touch}]},headers=h).status_code==409 # 封存后整批拒收
 assert client.post('/experiments/%s/archive'%i,json={},headers=h).status_code==409
 again=client.get('/experiments/%s'%i,headers=h).json()
 assert again['report']==frozen and again['receipt_count']==1 # 封存结果保持不变
def test_archive_receipts_race_all_or_nothing(client):
 d=make_experiment(client);i=d['id']
 batch=[{'event_id':'EV-%03d'%n,'code':m['code']} for n,m in enumerate(d['members']*20)]
 def post(path,payload,role):
  with TestClient(app) as c:
   t=c.post('/auth/login',json={'email':role+'@demo.local','password':'Demo123!'}).json()['token']
   return c.post(path,json=payload,headers={'Authorization':'Bearer '+t})
 with ThreadPoolExecutor(max_workers=2) as pool:
  rf=pool.submit(post,'/experiments/%s/receipts'%i,{'receipts':batch},'analyst')
  af=pool.submit(post,'/experiments/%s/archive'%i,{},'admin')
  receipts,archive=rf.result(),af.result()
 assert archive.status_code==200 # 封存必定成功
 with TestClient(app) as c:
  t=c.post('/auth/login',json={'email':'analyst@demo.local','password':'Demo123!'}).json()['token']
  final=c.get('/experiments/%s'%i,headers={'Authorization':'Bearer '+t}).json()
 if receipts.status_code==200: # 回执先完成：整批全收，封存结果包含它们
  assert receipts.json()['accepted']==len(batch)
  assert final['receipt_count']==len(batch)
  overall=[r for r in final['report']['rows'] if r['cluster_id'] is None][0]
  assert overall['touch']['read']==3 and overall['holdout']['read']==2
 else: # 封存先完成：整批全拒，结果无回执
  assert receipts.status_code==409
  assert final['receipt_count']==0
  overall=[r for r in final['report']['rows'] if r['cluster_id'] is None][0]
  assert overall['touch']['read']==0 and overall['holdout']['read']==0
 assert final['status']=='archived' and final['report']['live'] is False
