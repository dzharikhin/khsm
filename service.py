# coding=utf-8
import os
from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DateTime, UniqueConstraint, and_, or_, desc
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql.functions import count, max, coalesce, sum

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
def add_player(session, player_id, player_type, player_name, chat_id, initial_state, registration_time):
    """
    adds new player
    :param session: autoprovided via with_session
    :param player_id:
    :param player_name:
    :param player_type:
    :param chat_id:
    :param initial_state:
    :param registration_time:
    :return: new or existing player
    """
    existing_player = session.query(Player).filter(Player.player_id == player_id).first()
    if existing_player:
        return existing_player

    player = Player(player_id, player_type, player_name, chat_id, initial_state, registration_time)
    session.add(player)
    return player


@with_session()
def add_hint(session, player_id, question_id, hint_title):
    """
    adds hint usage
    :param session:
    :param player_id:
    :param question_id:
    :param hint_title:
    :return: True if already used, False - otherwise
    """
    used_hint = session.query(Hint).filter(and_(Hint.player_id == player_id, Hint.hint_title == hint_title)).first()
    if used_hint:
        return True
    new_hint = Hint(player_id, question_id, hint_title)
    session.add(new_hint)
    return False


@with_session()
def get_property(session, property_key, default_value):
    prop = session.query(Property).filter(Property.property_key == property_key).first()
    return prop.property_value if prop else default_value


@with_session()
def get_current_ctx(session, player_id, stage):
    answer = _get_last_answer(session, player_id, stage)
    return session.query(Player).filter(Player.player_id == player_id).first(), _get_next_unanswered_question(session, answer)


@with_session()
def reset_data(session):
    session.query(Answer).delete()
    session.query(Hint).delete()
    session.query(Player).delete()


@with_session()
def release_losers(session, stage, callback):
    losers = session.query(Player).filter(Player.state == 'LOSE').all()
    for loser in losers:
        session.begin_nested()
        answer = _get_last_answer(session, loser.player_id, stage)
        answer.tries = 1
        loser.state = 'REPEAT'
        session.commit()
        callback(loser)


@with_session()
def set_property(session, property_key, property_value):
    property = Property(property_key, property_value)
    session.add(property)
    session.query(Player).update({Player.state: 'PLAY'})
    session.commit()


@with_session()
def get_answer_stats(session, question_id):
    total = session.query(count('*')).select_from(Answer).filter(Answer.question_id == question_id).scalar()
    grouped_answers_query = session.query(Answer.variant_id, count('*').label('cnt')).group_by(Answer.variant_id)\
        .filter(Answer.question_id == question_id).subquery()
    grouped_answers = session.query(Variant.variant_id, coalesce(grouped_answers_query.c.cnt, 0))\
        .outerjoin(grouped_answers_query, grouped_answers_query.c.variant_id == Variant.variant_id)\
        .filter(Variant.question_id == question_id).all()
    return grouped_answers, total


@with_session()
def get_player_place(session, stage, player_id):
    rating_query = _get_rating(session, stage)
    all_rating = rating_query.subquery()
    player_score = rating_query.filter(Answer.player_id == player_id).first()
    if not player_score:
        return None
    return player_score, session.query(count('*') + 1).select_from(all_rating)\
        .filter(or_(all_rating.c.points > player_score[1],
                    and_(all_rating.c.points == player_score[1], all_rating.c.sum_tries < player_score[2]),
                    and_(all_rating.c.points == player_score[1], all_rating.c.sum_tries == player_score[2],
                         coalesce(all_rating.c.hint_count, 0) < player_score[3]),
                    and_(all_rating.c.points == player_score[1], all_rating.c.sum_tries == player_score[2],
                         coalesce(all_rating.c.hint_count, 0) == player_score[3], all_rating.c.last_answer_time < player_score[4]))).scalar()


@with_session()
def get_top(session, stage, top_size=None):
    question_amount = session.query(count(Question.question_id)).filter(Question.stage == stage).scalar()
    entities = _get_rating(session, stage)
    if top_size:
        entities = entities.limit(top_size)
    entities = entities.from_self().join(Player).with_entities(Player.player_name, 'points', 'sum_tries',
                                                               coalesce(Column('hint_count'), 0), 'last_answer_time', Player.chat_id,
                                                               Player.player_id) \
        .order_by(desc('points'), 'sum_tries', coalesce(Column('hint_count'), 0), 'last_answer_time')
    top = entities.all()
    return top, question_amount


@with_session()
def get_answer(session, player_id, question_id):
    return session.query(Answer).filter(and_(Answer.player_id == player_id, Answer.question_id == question_id)).first()


@with_session()
def get_question(session, question_id):
    return session.query(Question).filter(Question.question_id == question_id).first()


@with_session()
def process_answer(session, stage, player, variant_id, answer_time, try_limit):
    answer = _get_last_answer(session, player.player_id, stage)
    next_question = _get_next_unanswered_question(session, answer)
    if next_question:
        answer = _add_answer(session, player, next_question.question_id, variant_id, answer_time)
    state = _calculate_state(next_question, answer, try_limit)
    session.flush()
    return _set_user_state(session, player, state), _get_next_unanswered_question(session, answer)


@with_session()
def get_game_state(session, stage, player, try_limit):
    answer = _get_last_answer(session, player.player_id, stage)
    next_question = _get_next_unanswered_question(session, answer)
    return _calculate_state(next_question, answer, try_limit)


@with_session()
def set_player_state(session, player, state):
    return _set_user_state(session, player, state)


@with_session()
def save_player_contacts(session, player, text, state=None):
    player.contacts = text
    if state:
        player.state = state
    session.merge(player)
    return player


@with_session()
def get_players(sesion):
    return sesion.query(Player).all()


def _calculate_state(question, answer, try_limit):
    if not question:
        return 'WIN'
    if not answer:
        return 'INIT'
    if answer.tries > try_limit:
        return 'LOSE'
    elif answer.tries == try_limit:
        return 'PLAY' if answer.variant.correct else 'LOSE'
    else:
        return 'PLAY' if answer.variant.correct else 'REPEAT'


def _add_answer(session, player, question_id, variant_id, answer_time):
    existing_answer = session.query(Answer).filter(and_(Answer.player_id == player.player_id, Answer.question_id == question_id)).first()
    if existing_answer:
        session.begin_nested()
        existing_answer.tries += 1
        existing_answer.variant_id = variant_id
        existing_answer.answer_time = answer_time
        session.commit()
        session.refresh(existing_answer)
        return existing_answer

    answer = Answer(player.player_id, question_id, variant_id, answer_time, 1)
    session.begin_nested()
    session.add(answer)
    session.commit()
    return answer


def _get_last_answer(session, player_id, stage):
    return session.query(Answer).join(Question).filter(and_(Answer.player_id == player_id, Question.stage == stage)) \
        .order_by(desc(Question.weight)).first()


def _get_next_unanswered_question(session, answer=None):
    if not answer:
        return session.query(Question).order_by(Question.weight).first()
    if not answer.variant.correct:
        return answer.question
    return session.query(Question).filter(and_(Question.stage == answer.question.stage, Question.weight > answer.question.weight)) \
        .order_by(Question.weight).first()


def _set_user_state(session, player, state):
    player.state = state
    session.merge(player)
    return player


def _get_rating(session, stage):
    hint_usage_query = session.query(Hint.player_id, count(Hint.question_id).label('hint_count')).group_by(Hint.player_id).subquery()
    return session.query(Answer.player_id,
                         count(Answer.variant_id).label('points'),
                         max(Answer.answer_time).label('last_answer_time'),
                         sum(Answer.tries).label('sum_tries')) \
        .join(Answer.question).join(Answer.variant) \
        .filter(and_(Variant.correct == True, Question.stage == stage)) \
        .group_by(Answer.player_id) \
        .from_self()\
        .outerjoin(hint_usage_query, hint_usage_query.c.player_id == Answer.player_id)\
        .with_entities(Answer.player_id, 'points', 'sum_tries', 'hint_count', 'last_answer_time') \
        .order_by(desc('points'), 'sum_tries', coalesce(hint_usage_query.c.hint_count, 0), 'last_answer_time')


class Question(_Base):
    __tablename__ = 'question'
    question_id = Column(Integer, primary_key=True, nullable=False)

    stage = Column(Integer, nullable=False)
    text_value = Column(String(1000), nullable=False)
    weight = Column(Integer, nullable=False)

    # relations inited later
    variants = None


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
    chat_id = Column(Integer)
    state = Column(String(20), nullable=False)

    registration_time = Column(DateTime, nullable=False)
    contacts = Column(String(300))

    def __init__(self, player_id, player_type, player_name, chat_id, state, registration_time):
        self.player_id = player_id
        self.player_type = player_type
        self.player_name = player_name
        self.chat_id = chat_id
        self.state = state
        self.registration_time = registration_time


class Answer(_Base):
    __tablename__ = 'answer'
    player_id = Column(String(100), ForeignKey(Player.player_id), primary_key=True, nullable=False)
    question_id = Column(Integer, ForeignKey(Question.question_id), primary_key=True, nullable=False)

    variant_id = Column(String(1), ForeignKey(Variant.variant_id), nullable=False)
    tries = Column(Integer, nullable=False)
    answer_time = Column(DateTime, nullable=False)

    def __init__(self, player_id, question_id, variant_id, answer_time, tries):
        self.player_id = player_id
        self.question_id = question_id
        self.variant_id = variant_id
        self.answer_time = answer_time
        self.tries = tries

    # relations inited later
    question = None
    variant = None


class Hint(_Base):
    __tablename__ = 'hint'
    player_id = Column(String(100), ForeignKey(Player.player_id), primary_key=True, nullable=False)
    question_id = Column(Integer, ForeignKey(Question.question_id), primary_key=True, nullable=False)
    hint_title = Column(String(10), primary_key=True, nullable=False)

    def __init__(self, player_id, question_id, hint_title):
        self.player_id = player_id
        self.question_id = question_id
        self.hint_title = hint_title


class Property(_Base):
    __tablename__ = 'property'
    property_key = Column(String(20), primary_key=True, nullable=False)

    property_value = Column(String(1000))

    def __init__(self, property_key, property_value):
        self.property_key = property_key
        self.property_value = property_value


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
