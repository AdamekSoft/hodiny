# data_source.py

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from datetime import datetime
import uuid

Base = declarative_base()

# Asociativní tabulka pro projekty a fotografie
project_photos_table = Table('project_photos', Base.metadata,
                             Column('project_id', Integer, ForeignKey('projects.id')),
                             Column('photo_url', String)
                             )

class Worker(Base):
    __tablename__ = 'workers'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

class Project(Base):
    __tablename__ = 'projects'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    photos = relationship("Photo", back_populates="project")

class Photo(Base):
    __tablename__ = 'photos'
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey('projects.id'))
    project = relationship("Project", back_populates="photos")

class Record(Base):
    __tablename__ = 'records'
    id = Column(String, primary_key=True)
    date = Column(String, nullable=False)
    worker_id = Column(Integer, ForeignKey('workers.id'))
    project_id = Column(Integer, ForeignKey('projects.id'))
    start_time = Column(String, nullable=False)
    break_start = Column(String, nullable=False)
    break_end = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    hours = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    synced = Column(Integer, default=0)  # 0 = False, 1 = True

    worker = relationship("Worker")
    project = relationship("Project")

# Nový model pro API klíče
class APIKey(Base):
    __tablename__ = 'api_keys'
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)

class DataSource:
    def __init__(self, db_url='sqlite:///work_records.db'):
        self.engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.initialize_api_keys()

    # Inicializace s předem definovanými API klíči, pokud ještě nejsou přidány
    def initialize_api_keys(self):
        session = self.Session()
        existing_keys = session.query(APIKey).count()
        if existing_keys == 0:
            # Přidejte své API klíče zde
            predefined_keys = [
                {"key": "your_predefined_api_key_1", "description": "Mobile App Key"},
                {"key": "your_predefined_api_key_2", "description": "Backup Key"}
            ]
            for api_key in predefined_keys:
                new_key = APIKey(key=api_key["key"], description=api_key["description"])
                session.add(new_key)
            session.commit()
        session.close()

    # Pracovníci
    def get_workers(self):
        session = self.Session()
        workers = session.query(Worker).all()
        session.close()
        return [worker.name for worker in workers]

    def add_worker(self, worker_name):
        session = self.Session()
        if not session.query(Worker).filter_by(name=worker_name).first():
            new_worker = Worker(name=worker_name)
            session.add(new_worker)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    def remove_worker(self, worker_name):
        session = self.Session()
        worker = session.query(Worker).filter_by(name=worker_name).first()
        if worker:
            session.delete(worker)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    # Projekty
    def get_projects(self):
        session = self.Session()
        projects = session.query(Project).all()
        session.close()
        return [project.name for project in projects]

    def add_project(self, project_name):
        session = self.Session()
        if not session.query(Project).filter_by(name=project_name).first():
            new_project = Project(name=project_name)
            session.add(new_project)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    def remove_project(self, project_name):
        session = self.Session()
        project = session.query(Project).filter_by(name=project_name).first()
        if project:
            session.delete(project)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    # Záznamy
    def get_records_for_project(self, project_name):
        session = self.Session()
        project = session.query(Project).filter_by(name=project_name).first()
        if not project:
            session.close()
            return []
        records = session.query(Record).filter_by(project_id=project.id).all()
        session.close()
        return [self.record_to_dict(record) for record in records]

    def add_record(self, record):
        session = self.Session()
        if not session.query(Record).filter_by(id=record['id']).first():
            worker = session.query(Worker).filter_by(name=record['worker']).first()
            project = session.query(Project).filter_by(name=record['project']).first()
            if not worker or not project:
                session.close()
                return False
            new_record = Record(
                id=record.get('id', str(uuid.uuid4())),
                date=record['date'],
                worker_id=worker.id,
                project_id=project.id,
                start_time=record['start_time'],
                break_start=record['break_start'],
                break_end=record['break_end'],
                end_time=record['end_time'],
                hours=record['hours'],
                description=record.get('description', ''),
                synced=record.get('synced', 0)
            )
            session.add(new_record)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    def remove_record(self, record_id):
        session = self.Session()
        record = session.query(Record).filter_by(id=record_id).first()
        if record:
            session.delete(record)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    # Fotografie
    def get_photos_for_project(self, project_name):
        session = self.Session()
        project = session.query(Project).filter_by(name=project_name).first()
        if not project:
            session.close()
            return []
        photos = session.query(Photo).filter_by(project_id=project.id).all()
        session.close()
        return [photo.url for photo in photos]

    def add_photo_to_project(self, project_name, photo_url):
        session = self.Session()
        project = session.query(Project).filter_by(name=project_name).first()
        if project:
            new_photo = Photo(url=photo_url, project=project)
            session.add(new_photo)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    # API Klíče
    def get_api_keys(self):
        session = self.Session()
        keys = session.query(APIKey).all()
        session.close()
        return [api_key.key for api_key in keys]

    def add_api_key(self, key, description=''):
        session = self.Session()
        if not session.query(APIKey).filter_by(key=key).first():
            new_key = APIKey(key=key, description=description)
            session.add(new_key)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    def remove_api_key(self, key):
        session = self.Session()
        api_key = session.query(APIKey).filter_by(key=key).first()
        if api_key:
            session.delete(api_key)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    def verify_api_key(self, key):
        session = self.Session()
        exists = session.query(APIKey).filter_by(key=key).first() is not None
        session.close()
        return exists

    # Synchronizace
    def get_unsynced_records(self):
        session = self.Session()
        records = session.query(Record).filter_by(synced=0).all()
        session.close()
        return [self.record_to_dict(record) for record in records]

    def mark_record_as_synced(self, record_id):
        session = self.Session()
        record = session.query(Record).filter_by(id=record_id).first()
        if record:
            record.synced = 1
            session.commit()
            session.close()
            return True
        session.close()
        return False

    # Pomocné metody
    def record_to_dict(self, record):
        return {
            "id": record.id,
            "date": record.date,
            "worker": record.worker.name,
            "project": record.project.name,
            "start_time": record.start_time,
            "break_start": record.break_start,
            "break_end": record.break_end,
            "end_time": record.end_time,
            "hours": record.hours,
            "description": record.description,
            "synced": bool(record.synced)
        }

