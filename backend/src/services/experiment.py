import hashlib
def seed_for(segment_id,outreach_ids):
 return hashlib.sha256(('experiment:%s:%s'%(segment_id,','.join(map(str,sorted(outreach_ids))))).encode()).hexdigest()
def assign(members,seed):
 # 确定性均分：同一分群版本+同一组方案+同一会员编号永远得到同一组别，重试结果一致
 groups=[];by_cluster={}
 for m in members:by_cluster.setdefault(m['cluster_id'],set()).add(m['code'])
 for cid in sorted(by_cluster):
  ranked=sorted(by_cluster[cid],key=lambda c:hashlib.sha256(('%s:%s'%(seed,c)).encode()).hexdigest())
  half=(len(ranked)+1)//2
  for i,code in enumerate(ranked):groups.append(dict(code=code,cluster_id=cid,arm='touch' if i<half else 'holdout'))
 return groups
def summarize(members,read_codes):
 # 口径：分母为开实验时冻结分组的全体成员（含未阅读）；空组转化率为None，不报零
 rows=[]
 for cid in sorted({m['cluster_id'] for m in members})+[None]:
  group=[m for m in members if cid is None or m['cluster_id']==cid];row=dict(cluster_id=cid)
  for arm in ('touch','holdout'):
   codes={m['code'] for m in group if m['arm']==arm};read=len(codes&read_codes)
   row[arm]=dict(members=len(codes),read=read,rate=(read/len(codes) if codes else None))
  row['diff']=(row['touch']['rate']-row['holdout']['rate']) if row['touch']['rate'] is not None and row['holdout']['rate'] is not None else None
  rows.append(row)
 return rows
