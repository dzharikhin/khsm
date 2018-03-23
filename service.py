# coding=utf-8
import os
from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DateTime, UniqueConstraint, and_, desc
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base

import loggers

logger = loggers.logging.getLogger(__name__)

_Base = declarative_base()
_Session = sessionmaker(expire_on_commit=False)


def with_session():
    def decorator(func):
        def wrapper(*args, **kwargs):
            sess = _Session(autocommit=True, autoflush=True)
            try:
                sess.begin()
                result = func(sess, *args, **kwargs)
                sess.commit()
                return result
            except Exception as e:
                if sess is not None:
                    sess.rollback()
                logger.error('Error', exc_info=True)
                raise e
        return wrapper
    return decorator


@with_session()
def add_player(session, player_id, player_type, player_name, registration_time):
    """
    adds new player
    :param session: autoprovided via with_session
    :param player_id:
    :param player_name:
    :param player_type:
    :param registration_time:
    :return: False if player already exists, True - otherwise
    """
    existing_player = session.query(Player).filter(Player.player_id == player_id).first()
    if existing_player:
        return False
    player = Player(player_id, player_type, player_name, registration_time)
    session.add(player)
    return True


@with_session()
def add_answer(session, player_id, question_id, variant_id, answer_time):
    """
    adds player answer
    :param session: autoprovided via with_session
    :param player_id:
    :param question_id:
    :param variant_id:
    :param answer_time:
    :return: None if player already answered the question, Answer - otherwise
    """
    existing_answer = session.query(Answer).filter(and_(Answer.player_id == player_id, Answer.question_id == question_id)).first()
    if existing_answer:
        return None
    answer = Answer(player_id, question_id, variant_id, answer_time)
    session.add(answer)
    return answer


@with_session()
def get_property(session, property_key, default_value):
    prop = session.query(Property).filter(Property.property_key == property_key).first()
    return prop.property_value if prop else default_value


@with_session()
def get_last_answer(session, player_id, stage):
    return session.query(Answer).join(Question).filter(and_(Answer.player_id == player_id, Question.stage == stage))\
        .order_by(desc(Question.weight)).first()


@with_session()
def get_next_unanswered_question(session, answer=None):
    if not answer:
        return session.query(Question).order_by(Question.weight).first()
    if not answer.variant.correct:
        return answer.question
    return session.query(Question).filter(and_(Question.stage == answer.question.stage, Question.weight > answer.question.weight))\
        .order_by(Question.weight).first()


@with_session()
def reset_data(session):
    session.query(Answer).delete()
    session.query(Player).delete()


def get_answer_stats(session, question_id):
    pass


def get_player_place(session, stage, player_id):
    pass


def get_top(session, stage, top_size):
    pass


def get_right_answer_amount_for_questions(stage):
    pass


class Question(_Base):
    __tablename__ = 'question'
    question_id = Column(Integer, primary_key=True, nullable=False)

    stage = Column(Integer, nullable=False)
    text_value = Column(String(1000), nullable=False)
    weight = Column(Integer, nullable=False)


class Variant(_Base):
    __tablename__ = 'variant'
    question_id = Column(Integer, ForeignKey(Question.question_id), primary_key=True, nullable=False)
    variant_id = Column(String(1), primary_key=True, nullable=False)

    text_value = Column(String(1000), nullable=False)
    correct = Column(Boolean, nullable=False)

    __table_args__ = (UniqueConstraint(variant_id, question_id, correct, name='stupid_index_to_allow_foreign_key_to_variant_id'),)


class Player(_Base):
    __tablename__ = 'player'
    player_id = Column(String(100), primary_key=True, nullable=False)
    player_type = Column(String(3), primary_key=True, nullable=False)
    player_name = Column(String(100))

    registration_time = Column(DateTime, nullable=False)

    def __init__(self, player_id, player_type, player_name, registration_time):
        self.player_id = player_id
        self.player_type = player_type
        self.player_name = player_name
        self.registration_time = registration_time


class Answer(_Base):
    __tablename__ = 'answer'
    player_id = Column(String(100), ForeignKey(Player.player_id), primary_key=True, nullable=False)
    question_id = Column(Integer, ForeignKey(Question.question_id), primary_key=True, nullable=False)

    variant_id = Column(String(1), ForeignKey(Variant.variant_id), nullable=False)
    answer_time = Column(DateTime, nullable=False)

    def __init__(self, player_id, question_id, variant_id, answer_time):
        self.player_id = player_id
        self.question_id = question_id
        self.variant_id = variant_id
        self.answer_time = answer_time


class Property(_Base):
    __tablename__ = 'property'
    property_key = Column(String(20), primary_key=True, nullable=False)

    property_value = Column(String(1000))


def init():
    # relations
    Question.variants = relationship(Variant, order_by=Variant.variant_id, lazy='joined')
    Answer.question = relationship(Question, uselist=False, lazy='joined')
    Answer.variant = relationship(Variant, uselist=False, lazy='joined', primaryjoin=and_(Answer.question_id == Variant.question_id,
                                                                                          Answer.variant_id == Variant.variant_id))

    engine = create_engine('mysql+pymysql://{user}:{passwd}@{host}:{port}/{db}?charset=utf8'.format(**_build_parameters()),
                           isolation_level='READ_COMMITTED',
                           encoding='utf8',
                           echo=True)
    _Session.configure(bind=engine)
    _Base.metadata.create_all(engine)


def wait_for_db():
    _wait_for_db(int(os.environ.get('WAIT_FOR_DB_TRIES', 1)), int(os.environ.get('WAIT_FOR_DB_PAUSE_S', 0)))


def _wait_for_db(try_n, sleep_seconds):
    import pymysql
    import time
    try:
        pymysql.connect(**_build_parameters())
        print('DB is available')
    except Exception as e:
        if try_n == 1:
            print('DB is effectively unavailable, raising exception')
            raise e
        print('DB is not available yet, waiting')
        time.sleep(sleep_seconds)
        _wait_for_db(try_n - 1, sleep_seconds)


def _build_parameters():
    return {'user': os.environ['DB_USER'],
            'passwd': os.environ['DB_PASS'],
            'host': os.environ['DB_HOST'],
            'port': int(os.environ['DB_PORT']),
            'db': os.environ['DB_NAME']}
