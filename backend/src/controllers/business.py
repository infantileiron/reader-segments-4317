from fastapi import HTTPException
from src.models.entities import Segment,Experiment
def ensure_segment(s,i):
 row=s.get(Segment,i)
 if not row:raise HTTPException(404,'分群版本不存在')
 return row
def ensure_experiment(s,i):
 row=s.get(Experiment,i)
 if not row:raise HTTPException(404,'对照实验不存在')
 return row
