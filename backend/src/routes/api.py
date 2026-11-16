import os,json
from datetime import datetime,timezone
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import User,Reader,Segment,Outreach,Experiment,ExperimentMember,Receipt,Quarantine,Audit
from src.schemas.business import Login,ReaderInput,SegmentInput,OutreachInput,ExperimentInput,ReceiptBatch
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.services.experiment import seed_for,assign,summarize
from src.controllers.business import ensure_segment,ensure_experiment
router=APIRouter()
def now():return datetime.now(timezone.utc).isoformat()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/readers')
def readers(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Reader).order_by(Reader.id).all()]
@router.post('/readers')
def create(data:ReaderInput,u=Depends(editor),s=Depends(db)):
 r=Reader(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'会员编号重复')
 audit(s,u,'录入阅读档案 '+r.code);return dump(r)
@router.put('/readers/{i}')
def edit(i:int,data:ReaderInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Reader,i)
 if not r:raise HTTPException(404,'会员档案不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'会员编号重复')
 audit(s,u,'修订档案 '+str(i));return dump(r)
@router.get('/segments')
def segments(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Segment).order_by(Segment.id.desc()).all()]
@router.post('/segments')
def train(data:SegmentInput,u=Depends(editor),s=Depends(db)):
 rows=[dump(r) for r in s.query(Reader).order_by(Reader.id).all()];r=Segment(**data.model_dump(),result={'snapshot':rows});s.add(r);s.commit()
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('reader:segments',r.id)
 except redis.RedisError:r.state='failed';r.error='队列暂不可用，请稍后重试';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交分群 '+str(r.id));return dump(r)
@router.get('/segments/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_segment(s,i))
@router.get('/segments/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_segment(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功分群可导出')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="reader-segments-{i}.json"'})
@router.get('/outreaches')
def outreaches(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Outreach).order_by(Outreach.id.desc()).all()]
@router.post('/outreaches')
def outreach(data:OutreachInput,u=Depends(editor),s=Depends(db)):
 r=ensure_segment(s,data.segment_id)
 if r.state!='done':raise HTTPException(409,'分群完成后才能制定触达方案')
 members=[m['code'] for m in r.result['members'] if m['cluster_id']==data.cluster_id]
 if not members:raise HTTPException(422,'该版本没有所选群组')
 o=Outreach(**data.model_dump(),members=members);s.add(o);s.commit();audit(s,u,'起草触达方案 '+str(o.id));return dump(o)
@router.post('/outreaches/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=s.get(Outreach,i)
 if not r:raise HTTPException(404,'触达方案不存在')
 if r.status!='draft':raise HTTPException(409,'已签核方案不可重复签核')
 r.status='approved';s.commit();audit(s,u,'签核触达方案 '+str(i));return dump(r)
@router.get('/outreaches/{i}/export')
def export_outreach(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(Outreach,i)
 if not r:raise HTTPException(404,'触达方案不存在')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="reader-outreach-{i}.json"'})
def experiment_payload(s,e):
 members=[dump(m) for m in s.query(ExperimentMember).filter_by(experiment_id=e.id).order_by(ExperimentMember.cluster_id,ExperimentMember.arm,ExperimentMember.code).all()]
 quarantine=[dump(q) for q in s.query(Quarantine).filter_by(experiment_id=e.id).order_by(Quarantine.id).all()]
 receipt_count=s.query(Receipt).filter_by(experiment_id=e.id).count()
 if e.status=='archived' and e.result:report={**e.result,'live':False}
 else:report=dict(rows=summarize(members,{r.code for r in s.query(Receipt.code).filter_by(experiment_id=e.id)}),live=True)
 return {**dump(e),'members':members,'quarantine':quarantine,'receipt_count':receipt_count,'report':report}
@router.get('/experiments')
def experiments(u=Depends(current),s=Depends(db)):
 out=[]
 for e in s.query(Experiment).order_by(Experiment.id.desc()).all():
  d=dump(e);d['member_count']=s.query(ExperimentMember).filter_by(experiment_id=e.id).count();d['receipt_count']=s.query(Receipt).filter_by(experiment_id=e.id).count();out.append(d)
 return out
@router.post('/experiments')
def create_experiment(data:ExperimentInput,u=Depends(editor),s=Depends(db)):
 seg=ensure_segment(s,data.segment_id)
 if seg.state!='done':raise HTTPException(409,'分群完成后才能开启对照实验')
 ids=sorted(set(data.outreach_ids));plans=[s.get(Outreach,o) for o in ids]
 if any(p is None for p in plans):raise HTTPException(404,'触达方案不存在')
 for p in plans:
  if p.segment_id!=data.segment_id:raise HTTPException(422,'只能合并同一分群版本的已签核方案')
  if p.status!='approved':raise HTTPException(409,'仅已签核方案可并入对照实验')
 cluster_of={m['code']:m['cluster_id'] for m in seg.result['members']};merged={}
 for p in plans:
  for code in p.members:
   if code in cluster_of:merged.setdefault(code,cluster_of[code])
 if not merged:raise HTTPException(422,'所选方案没有可分组的会员')
 seed=seed_for(data.segment_id,ids);groups=assign([dict(code=c,cluster_id=cid) for c,cid in merged.items()],seed)
 e=Experiment(segment_id=data.segment_id,title=data.title,note=data.note,outreach_ids=ids,seed=seed,status='running',created=now(),updated=now())
 s.add(e);s.flush()
 for g in groups:s.add(ExperimentMember(experiment_id=e.id,**g))
 s.commit();audit(s,u,'开启对照实验 '+str(e.id));return experiment_payload(s,e)
@router.get('/experiments/{i}')
def experiment_detail(i:int,u=Depends(current),s=Depends(db)):return experiment_payload(s,ensure_experiment(s,i))
@router.get('/experiments/{i}/export')
def export_experiment(i:int,u=Depends(current),s=Depends(db)):
 e=ensure_experiment(s,i)
 touch=sorted(m.code for m in s.query(ExperimentMember.code).filter_by(experiment_id=i,arm='touch'))
 payload=dict(id=e.id,title=e.title,segment_id=e.segment_id,outreach_ids=e.outreach_ids,status=e.status,created=e.created,arm='touch',members=touch)
 return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="experiment-touch-{i}.json"'})
@router.post('/experiments/{i}/receipts')
def receive_receipts(i:int,data:ReceiptBatch,u=Depends(editor),s=Depends(db)):
 stamp=now()
 # 守卫更新是事务首条语句并与封存互斥：仅进行中实验可入账，整批同事务提交，全收或全拒
 guard=s.execute(update(Experiment).where(Experiment.id==i,Experiment.status=='running').values(updated=stamp))
 if guard.rowcount==0:
  s.rollback();ensure_experiment(s,i);raise HTTPException(409,'实验已封存，整批回执拒收')
 roster={m.code for m in s.query(ExperimentMember.code).filter_by(experiment_id=i)}
 seen={r.event_id for r in s.query(Receipt.event_id).filter_by(experiment_id=i)}
 seen|={q.event_id for q in s.query(Quarantine.event_id).filter_by(experiment_id=i)}
 accepted=replayed=quarantined=0
 for item in data.receipts:
  if item.event_id in seen:replayed+=1;continue
  seen.add(item.event_id)
  if item.code in roster:s.add(Receipt(experiment_id=i,event_id=item.event_id,code=item.code,created=stamp));accepted+=1
  else:s.add(Quarantine(experiment_id=i,event_id=item.event_id,code=item.code,reason='会员不在实验名单',created=stamp));quarantined+=1
 s.commit();audit(s,u,'接收实验 %s 回执 %s 条'%(i,accepted))
 return {'accepted':accepted,'replayed':replayed,'quarantined':quarantined}
@router.post('/experiments/{i}/archive')
def archive_experiment(i:int,u=Depends(editor),s=Depends(db)):
 stamp=now()
 guard=s.execute(update(Experiment).where(Experiment.id==i,Experiment.status=='running').values(status='archived',archived=stamp,updated=stamp))
 if guard.rowcount==0:
  s.rollback();ensure_experiment(s,i);raise HTTPException(409,'实验已封存，结果保持不变')
 members=[dump(m) for m in s.query(ExperimentMember).filter_by(experiment_id=i).all()]
 read_codes={r.code for r in s.query(Receipt.code).filter_by(experiment_id=i)}
 s.execute(update(Experiment).where(Experiment.id==i).values(result=dict(rows=summarize(members,read_codes),archived=stamp)))
 s.commit();audit(s,u,'封存对照实验 '+str(i));return experiment_payload(s,ensure_experiment(s,i))
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
