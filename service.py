# coding=utf-8
import os
from telegram.ext import Updater
from sqlalchemy import Column, ForeignKey, Integer, String, Boolean, DateTime, ForeignKeyConstraint, and_, or_
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql.functions import count, max, dense_rank, sum as sum_

import loggers

logger = loggers.logging.getLogger(__name__)

_Base = declarative_base()
_Session = sessionmaker(expire_on_commit=False)

BOT_TOP_LIMIT = 'bot_top_limit'
BOT_ANSWER_TRY_LIMIT = 'bot_answer_try_limit'
BOT_HINT_TRY_LIMIT = 'bot_hint_try_limit'
FIFTY_HINT_TITLE_TEXT = 'fifty_hint_title_text'
PUBLIC_HELP_HINT_TITLE_TEXT = 'public_help_hint_title_text'

FIFTY_HINT_KEY = 'fifty'
PUBLIC_HELP_HINT_KEY = 'public_help'
AVAILABLE_HINTS = [{'hint_key': FIFTY_HINT_KEY, 'title_key': FIFTY_HINT_TITLE_TEXT},
                   {'hint_key': PUBLIC_HELP_HINT_KEY, 'title_key': PUBLIC_HELP_HINT_TITLE_TEXT}]


def create_updater(token, workers, request_kwargs):
    return Updater(token, request_kwargs=request_kwargs, workers=int(workers))


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


def _id_from(user):
    return str(user.id)


@with_session()
def get_property(session, property_key, default_value):
    return _get_property(session, property_key, default_value)


def _get_property(session, property_key, default_value):
    prop = session.query(Property).filter(Property.property_key == property_key).first()
    return prop.property_value if prop else default_value


@with_session()
def add_player(session, user, chat_id, registration_time):
    return _add_player(session, user, user.name, chat_id, registration_time)


def _add_player(session, user, name, chat_id, registration_time):
    player_id = _id_from(user)
    existing_player = _get_player_query(session, player_id).first()
    if existing_player:
        return existing_player
    player = Player(player_id, name, chat_id, registration_time)
    session.add(player)
    return player


def _get_player_query(session, player_id):
    return session.query(Player).filter(Player.player_id == player_id)


@with_session()
def get_overlimited_answer(session, user):
    try_limit = int(_get_property(session, BOT_ANSWER_TRY_LIMIT, 2))
    return _tries_minus_answers(session, _id_from(user)) > try_limit


@with_session()
def get_max_question_id(session):
    return session.query(max(Question.question_id)).scalar()


@with_session()
def get_max_passed_question_id(session, user):
    max_passed_question_for_user = session.query(max(Question.question_id)).join(Variant).join(Answer).filter(
        and_(Answer.player_id == _id_from(user), Answer.passed == True)).scalar()
    return max_passed_question_for_user if max_passed_question_for_user else 0


@with_session()
def get_question(session, question_id):
    return session.query(Question).filter(Question.question_id == question_id).one()


@with_session()
def get_available_hints(session, user):
    used_hint_keys = [hint_key for hint_key, in session.query(Hint.hint_key).filter(Hint.player_id == _id_from(user)).all()]
    return [{'hint_key': hint['hint_key'], 'hint_title': _get_property(session, hint['title_key'], 'unknown')}
            for hint in AVAILABLE_HINTS if hint['hint_key'] not in used_hint_keys]


@with_session()
def add_answer(session, user, question_id, variant_id, answer_time):
    """
    :return: if question passed or if more tries available
    """
    player_id = _id_from(user)
    answer = session.query(Answer).join(Variant).filter(and_(Answer.player_id == player_id, Variant.question_id == question_id)).first()
    if answer:
        answer.answer_time = answer_time
    else:
        answer = Answer(player_id, question_id, variant_id, answer_time)
        session.add(answer)

    answer.tries += 1
    session.add(answer)
    # tries incremented but not committed yet
    try_limit = int(_get_property(session, BOT_ANSWER_TRY_LIMIT, 2))
    if not _is_variant_correct(session, question_id, variant_id):
        return _tries_minus_answers(session, player_id) < try_limit - 1

    answer.passed = answer.tries <= try_limit
    return answer.passed


def _tries_minus_answers(session, player_id):
    return session.query(sum_(Answer.tries) - count(Answer.answer_time)).filter(Answer.player_id == player_id).scalar()


def _is_variant_correct(session, question_id, variant_id):
    return session.query(Variant.correct).filter(Variant.question_id == question_id, Variant.variant_id == variant_id).scalar()


@with_session()
def add_hint(session, user, hint_key, question_id):
    player_id = _id_from(user)
    hint = session.query(Hint).filter(and_(Hint.player_id == player_id, Hint.hint_key == hint_key)).first()
    if hint:
        hint.tries += 1
        hint.question_id = question_id
    else:
        hint = Hint(player_id, question_id, hint_key, 1)
        session.add(hint)

    hint_try_limit = int(_get_property(session, BOT_HINT_TRY_LIMIT, 1))
    return hint.tries <= hint_try_limit


@with_session()
def get_answer_stats(session, question_id):
    answers_distribution = session.query(Answer.variant_id, count('*').label('cnt')).select_from(Answer).join(Variant).join(Question).filter(
        Question.question_id == question_id).group_by(Answer.variant_id).all()
    return answers_distribution, sum([row[1] for row in answers_distribution])


@with_session()
def get_user_place(session, user):
    position_field, rating_query = _build_rating_query(session)
    return rating_query.from_self(position_field).filter(Player.player_id == _id_from(user)).scalar()


def _build_rating_query(session):
    passed_answers_query = session.query(Answer.player_id,
                                         count('*').label('points'),
                                         sum_(Answer.tries).label('tries'),
                                         max(Answer.answer_time).label('last_answer_time')).filter(Answer.passed == True) \
        .group_by(Answer.player_id).subquery()
    hint_count_query = session.query(Hint.player_id, count('*').label('hint_count')).group_by(Hint.player_id).subquery()

    position_field = dense_rank().over(order_by=[passed_answers_query.c.points.desc().nullslast(),
                                                 passed_answers_query.c.tries.nullslast(),
                                                 hint_count_query.c.hint_count.nullsfirst(),
                                                 passed_answers_query.c.last_answer_time.nullslast()]).label('position')

    return position_field, session.query(position_field,
                                         Player,
                                         passed_answers_query.c.points,
                                         passed_answers_query.c.tries,
                                         hint_count_query.c.hint_count,
                                         passed_answers_query.c.last_answer_time) \
        .select_from(Player) \
        .outerjoin(passed_answers_query, Player.player_id == passed_answers_query.c.player_id) \
        .outerjoin(hint_count_query, Player.player_id == hint_count_query.c.player_id).order_by(position_field)


@with_session()
def get_top(session, limited=True):
    position_field, rating_query = _build_rating_query(session)
    if limited:
        top_size = _get_property(session, BOT_TOP_LIMIT, 10)
        rating_query = rating_query.limit(top_size)
    return rating_query.all()


@with_session()
def get_properties(session):
    return session.query(Property).order_by(Property.property_key)


@with_session()
def save_properties(session, properties):
    props = session.query(Property).filter(Property.property_key.in_(properties.keys())).all()
    for prop in props:
        prop.property_value = properties[prop.property_key]


@with_session()
def clear_data(session, player_ids):
    session.query(Answer).filter(Answer.player_id.in_(player_ids)).delete(synchronize_session=False)
    session.query(Hint).filter(Hint.player_id.in_(player_ids)).delete(synchronize_session=False)


@with_session()
def get_player(session, player_id):
    return _get_player_query(session, player_id).one()


@with_session()
def rename_player(session, player_id, player_name):
    player = session.query(Player).filter(Player.player_id == player_id).one()
    player.player_name = player_name


class Player(_Base):
    __tablename__ = 'player'
    player_id = Column(String(100), primary_key=True, nullable=False)

    player_name = Column(String(100))
    chat_id = Column(Integer)

    registration_time = Column(DateTime, nullable=False)

    def __init__(self, player_id, player_name, chat_id, registration_time):
        self.player_id = player_id
        self.player_name = player_name
        self.chat_id = chat_id
        self.registration_time = registration_time


class Question(_Base):
    __tablename__ = 'question'
    question_id = Column(Integer, primary_key=True, nullable=False)

    text_value = Column(String(1000), nullable=False)

    # relations inited later
    variants = None


class Variant(_Base):
    __tablename__ = 'variant'
    variant_id = Column(String(1), primary_key=True, nullable=False)
    question_id = Column(Integer, ForeignKey(Question.question_id), primary_key=True, nullable=False)

    text_value = Column(String(1000), nullable=False)
    correct = Column(Boolean, nullable=False)


class Answer(_Base):
    __tablename__ = 'answer'
    player_id = Column(String(100), ForeignKey(Player.player_id), primary_key=True, nullable=False)
    question_id = Column(Integer, primary_key=True, nullable=False)
    variant_id = Column(String(1), primary_key=True, nullable=False)

    tries = Column(Integer, nullable=False)
    passed = Column(Boolean)
    answer_time = Column(DateTime, nullable=False)

    def __init__(self, player_id, question_id, variant_id, answer_time):
        self.player_id = player_id
        self.question_id = question_id
        self.variant_id = variant_id
        self.answer_time = answer_time
        self.tries = 0

    __table_args__ = (ForeignKeyConstraint((question_id, variant_id), [Variant.question_id, Variant.variant_id]),)

    # relations inited later
    # variant = None


class Hint(_Base):
    __tablename__ = 'hint'
    player_id = Column(String(100), ForeignKey(Player.player_id), primary_key=True, nullable=False)
    question_id = Column(Integer, ForeignKey(Question.question_id), primary_key=True, nullable=False)
    hint_key = Column(String(50), primary_key=True, nullable=False)
    tries = Column(Integer, nullable=False)

    def __init__(self, player_id, question_id, hint_key, tries):
        self.player_id = player_id
        self.question_id = question_id
        self.hint_key = hint_key
        self.tries = tries


class Property(_Base):
    __tablename__ = 'property'
    property_key = Column(String(50), primary_key=True, nullable=False)

    property_value = Column(String(1000))

    def __init__(self, property_key, property_value):
        self.property_key = property_key
        self.property_value = property_value


def init():
    # relations
    Question.variants = relationship(Variant, order_by=Variant.variant_id, lazy='joined')
    # Answer.variant = relationship(Variant, uselist=False, lazy='dynamic', primaryjoin=and_(Answer.question_id == Variant.question_id,
    #                                                                                        Answer.variant_id == Variant.variant_id))

    engine = create_engine('postgresql+psycopg2://{user}:{passwd}@{host}:{port}/{db}'.format(**_build_parameters()),
                           isolation_level='READ_COMMITTED',
                           encoding='utf8',
                           echo=True)
    _Session.configure(bind=engine)
    _Base.metadata.create_all(engine)


def _build_parameters():
    return {'user': os.environ['DB_USER'],
            'passwd': os.environ['DB_PASS'],
            'host': os.environ['DB_HOST'],
            'port': int(os.environ['DB_PORT']),
            'db': os.environ['DB_NAME']}
