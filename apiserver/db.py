from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from config import config

# Declarative base class
Base = declarative_base()
Base.query = db_session.query_property()


class Export(Base):
    # table name
    __tablename__ = config.table
    # table schema
    export_id = Column(Integer, primary_key=True)
    user_name = Column(String(64), unique=True)
    status = Column(Integer)
    quota = Column(String(10))
    location = Column(String(256))
    volume_name = Column(String(64))
    iptable = Column(String(500))
    guest = Column(String(500))
    create_time = Column(DateTime)
    update_time = Column(DateTime)
    description = Column(String(256))

    def __init__(self, user_name, status, quota, location, volume_name, create_time, iptable=None, guest=None, update_time=None, description=None):
        self.user_name = user_name
        self.status = status
        self.quota = quota
        self.location = location
        self.volume_name = volume_name
        self.iptable = iptable
        self.guest = guest
        self.create_time = create_time
        self.update_time = update_time
        self.description = description

    def __repr__(self):
        return '<Class Export %r>' % self.name


# Create an Engine for database connection
engine = create_engine(config.db, convert_unicode=True, pool_recycle=7200)
# Sessionmaker factory generates new Session object, which is the handler to database. scoped_session for thread safety
db_session = scoped_session(sessionmaker(autocommit=False, autoflash=False, bind=engine))


def init_db():
    # create table in the database
    Base.metadata.create_all(bind=engine)
