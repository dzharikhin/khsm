# coding=utf-8

import datetime
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

import loggers
import service

logger = loggers.logging.getLogger(__name__)
PLAYER_TYPE = 'TG'
BOT_STAGE = 'bot_stage'
BOT_GREETING_TEXT = 'bot_greeting_text'
BOT_WIN_TEXT = 'bot_win_text'
BOT_FINAL_TEXT = 'bot_final_text'
BOT_LOSE_TEXT = 'bot_lose_text'
BOT_ALREADY_ANSWERED_TEXT = 'bot_already_answered_question_text'
BOT_PLACE_TEXT = 'bot_place_text'
BOT_HELP_TEXT = 'bot_help_text'

BOT_SKIP_REPLY = 'bot_skip_reply'


def start_handler(bot, update):
    player = update.message.from_user
    player_id = str(player.id)
    is_new_user = service.add_player(player_id, PLAYER_TYPE, player.username, update.message.chat_id, datetime.datetime.now())
    if is_new_user:
        greeting = service.get_property(BOT_GREETING_TEXT, 'Добро пожаловать в игру')
        _reply_to_player(update.message, greeting)

    current_stage = service.get_property(BOT_STAGE, '1')
    answer = service.get_last_answer(player_id, current_stage)
    _process_question(bot, answer, update.message)


def _process_question(bot, latest_answer, message):
    next_question = service.get_next_unanswered_question(latest_answer)
    if not next_question:
        _reply_to_player(message, service.get_property(BOT_WIN_TEXT, 'Поздравляем, Ваш успешно ответили на все вопросы'))
        # my_place_handler(bot, update)
        _reply_to_player(message, service.get_property(BOT_FINAL_TEXT, 'Следите за анонсами'))
    elif not latest_answer or next_question.question_id != latest_answer.question_id:
        _reply_to_player(message, text=next_question.text_value, reply_markup=_build_keyboard(next_question), force_reply=True)
    else:
        _reply_to_player(message, service.get_property(BOT_LOSE_TEXT, 'К сожалению, Ваша игра - окончена. Спасибо за участие'))
        # my_place_handler(bot, update)
        _reply_to_player(message, service.get_property(BOT_FINAL_TEXT, 'Следите за анонсами'))


def button_handler(bot, callback_update):
    user = callback_update.effective_user
    player_id = str(user.id)
    latest_answer, current_question = _get_state(player_id)
    if current_question:
        variant_id = callback_update.callback_query.data
        latest_answer = service.add_answer(player_id, current_question.question_id, variant_id, datetime.datetime.now())
        if not latest_answer:
            text = service.get_property(BOT_ALREADY_ANSWERED_TEXT, 'Вы уже ответили на этот вопрос')
            _reply_to_player(callback_update.effective_message, text)
            return
        _process_question(bot, latest_answer, callback_update.effective_message)


def _get_state(player_id):
    current_stage = service.get_property(BOT_STAGE, '1')
    latest_answer = service.get_last_answer(player_id, current_stage)
    current_question = service.get_next_unanswered_question(latest_answer)
    return latest_answer, current_question


def hint_handler(bot, update):
    user = update.message.from_user
    player_id = str(user.id)
    latest_answer, current_question = _get_state(player_id)
    if not current_question:
        _reply_to_player(update.message, service.get_property(BOT_WIN_TEXT, 'Поздравляем, Ваш успешно ответили на все вопросы'))
    grouped, total = service.get_answer_stats(current_question.question_id)
    text = '\n'.join(['{} - {}%'.format(variant[0], variant[1] / float(total) * 100 if total else 0) for variant in grouped])
    _reply_to_player(update.message, text)


def my_place_handler(bot, update):
    current_stage = service.get_property(BOT_STAGE, '1')
    user = update.message.from_user
    player_id = str(user.id)

    place = service.get_player_place(current_stage, player_id)
    if not place:
        _reply_to_player(update.message, service.get_property(BOT_GREETING_TEXT, 'Добро пожаловать в игру'))
    else:
        template = service.get_property(BOT_PLACE_TEXT, 'Сейчас вы на {} месте')
        _reply_to_player(update.message, template.format(place))


def top_handler(bot, update):
    current_stage = service.get_property(BOT_STAGE, '1')
    top, question_amount = service.get_top(current_stage, 10)
    text = '\n'.join(['{}. {}{}'.format(i + 1, player[0], "(*)" if player[1] == question_amount else "") for i, player in enumerate(top)])
    _reply_to_player(update.message, text)


def help_handler(bot, update):
    help_text = service.get_property(BOT_HELP_TEXT, 'Шлите /start или любое другое сообщение, чтобы начать')
    _reply_to_player(update.message, help_text)


def error(bot, update, err):
    logger.warning("Update '%s' caused error '%s'", update, err)


def _reply_to_player(message, text, *args, **kwargs):
    if not service.get_property(BOT_SKIP_REPLY, '') or kwargs.get('force_reply', False):
        message.reply_text(text, *args, **kwargs)


def _build_keyboard(question):
    options = [InlineKeyboardButton(variant.text_value, callback_data=variant.variant_id)
               for variant in question.variants]
    return InlineKeyboardMarkup(_build_menu(options, n_cols=1))


def _build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


def main():
    updater = Updater(os.environ['BOT_TOKEN'])

    updater.dispatcher.add_handler(CommandHandler('help', help_handler))
    updater.dispatcher.add_handler(CommandHandler('start', start_handler))
    updater.dispatcher.add_handler(CommandHandler('hint', hint_handler))
    updater.dispatcher.add_handler(CommandHandler('myplace', my_place_handler))
    updater.dispatcher.add_handler(CommandHandler('top', top_handler))
    updater.dispatcher.add_handler(CallbackQueryHandler(button_handler))
    updater.dispatcher.add_handler(MessageHandler(Filters.all, start_handler))
    updater.dispatcher.add_error_handler(error)

    updater.start_polling()
    updater.idle()
