from pydantic import BaseModel,Field,field_validator
from typing import Literal
class Login(BaseModel):email:str;password:str
class ReaderInput(BaseModel):
 code:str=Field(min_length=1,max_length=60)
 weekly_reading:float=Field(ge=0,le=1000,allow_inf_nan=False)
 completion:float=Field(ge=0,le=1,allow_inf_nan=False)
 night_share:float=Field(ge=0,le=1,allow_inf_nan=False)
 note:str=Field(default='',max_length=1000)
class SegmentInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 k:int=Field(default=3,ge=2,le=6)
 features:list[Literal['weekly_reading','completion','night_share']]=Field(default=['weekly_reading','completion','night_share'],min_length=2,max_length=3)
 @field_validator('features')
 @classmethod
 def unique(cls,v):
  if len(set(v))!=len(v):raise ValueError('特征不能重复')
  return v
class OutreachInput(BaseModel):
 segment_id:int=Field(gt=0)
 cluster_id:int=Field(ge=0,le=5)
 title:str=Field(min_length=2,max_length=100)
 note:str=Field(min_length=8,max_length=2000)
class ExperimentInput(BaseModel):
 segment_id:int=Field(gt=0)
 outreach_ids:list[int]=Field(min_length=1,max_length=50)
 title:str=Field(min_length=2,max_length=100)
 note:str=Field(min_length=8,max_length=2000)
class ReceiptItem(BaseModel):
 event_id:str=Field(min_length=1,max_length=60)
 code:str=Field(min_length=1,max_length=60)
class ReceiptBatch(BaseModel):
 receipts:list[ReceiptItem]=Field(min_length=1,max_length=5000)
