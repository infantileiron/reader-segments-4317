from sqlalchemy import Column,Integer,String,Float,JSON,Text,ForeignKey,UniqueConstraint
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True);password=Column(String(200));role=Column(String(20))
class Reader(Base):
 __tablename__='readers'
 id=Column(Integer,primary_key=True);code=Column(String(60),unique=True,nullable=False);weekly_reading=Column(Float);completion=Column(Float);night_share=Column(Float);note=Column(Text,default='')
class Segment(Base):
 __tablename__='segments'
 id=Column(Integer,primary_key=True);name=Column(String(100));k=Column(Integer);features=Column(JSON);state=Column(String(20),default='queued');result=Column(JSON);error=Column(Text,default='')
class Outreach(Base):
 __tablename__='outreaches'
 id=Column(Integer,primary_key=True);segment_id=Column(Integer,ForeignKey('segments.id'));cluster_id=Column(Integer);title=Column(String(100));note=Column(Text);members=Column(JSON);status=Column(String(20),default='draft')
class Experiment(Base):
 __tablename__='experiments'
 id=Column(Integer,primary_key=True);segment_id=Column(Integer,ForeignKey('segments.id'));title=Column(String(100));note=Column(Text);outreach_ids=Column(JSON);seed=Column(String(64));status=Column(String(20),default='running');result=Column(JSON);created=Column(String(40));updated=Column(String(40),default='');archived=Column(String(40),default='')
class ExperimentMember(Base):
 __tablename__='experiment_members'
 __table_args__=(UniqueConstraint('experiment_id','code'),)
 id=Column(Integer,primary_key=True);experiment_id=Column(Integer,ForeignKey('experiments.id'));code=Column(String(60));cluster_id=Column(Integer);arm=Column(String(10))
class Receipt(Base):
 __tablename__='receipts'
 __table_args__=(UniqueConstraint('experiment_id','event_id'),)
 id=Column(Integer,primary_key=True);experiment_id=Column(Integer,ForeignKey('experiments.id'));event_id=Column(String(60));code=Column(String(60));created=Column(String(40))
class Quarantine(Base):
 __tablename__='quarantines'
 __table_args__=(UniqueConstraint('experiment_id','event_id'),)
 id=Column(Integer,primary_key=True);experiment_id=Column(Integer,ForeignKey('experiments.id'));event_id=Column(String(60));code=Column(String(60));reason=Column(String(200));created=Column(String(40))
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
