# coding=utf-8

import datetime
import os
import random

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, Filters

import loggers
import service

logger = loggers.logging.getLogger(__name__)

BOT_RETRY_TEXT = 'bot_retry_text'
BOT_WIN_TEXT = 'bot_win_text'
BOT_LOSE_TEXT = 'bot_lose_text'

BOT_PLACE_TEXT = 'bot_place_text'

BOT_HELP_TEXT = 'bot_help_text'

BOT_HINT_UNAVAILABLE_TEXT = 'bot_hint_unavailable_text'
BOT_FIFTY_FOR_TWO_TEXT = 'bot_fifty_for_two_text'


def start_handler(_, update):
    user = update.effective_user
    player = service.add_player(user, update.effective_message.chat_id, datetime.datetime.now())
    logger.info('Player id={} wrote {}'.format(player.player_id, update.effective_message.text))
    overdraft = service.is_overdrafted(user)
    _handle_message(user, update, overdraft)


def answer_button_handler(_, callback_update):
    user = callback_update.effective_user
    overdraft = service.is_overdrafted(user)
    if overdraft:
        _release_inline_button(callback_update)
        return

    _, question_id, variant_id = json.loads(callback_update.callback_query.data)
    max_user_answered_question_id = service.get_max_passed_question_id(user)
    if max_user_answered_question_id >= question_id:
        _release_inline_button(callback_update)
        return

    fail = not service.add_answer(user, question_id, variant_id, datetime.datetime.now())
    _handle_message(user, callback_update, fail, current_question_id=question_id)


def hint_button_handler(_, callback_update):
    user = callback_update.effective_user
    overdraft = service.is_overdrafted(user)
    if overdraft:
        _release_inline_button(callback_update)
        return

    _, hint_key, question_id = json.loads(callback_update.callback_query.data)
    max_user_answered_question_id = service.get_max_passed_question_id(user)
    if max_user_answered_question_id >= question_id:
        _release_inline_button(callback_update)
        return

    hint_available = service.add_hint(user, hint_key, question_id)
    if not hint_available:
        already_used = service.get_property(BOT_HINT_UNAVAILABLE_TEXT, "Подсказка уже использована")
        _show_notification_if_possible(callback_update, already_used)
        return

    if service.FIFTY_HINT_KEY == hint_key:
        callback_answered = _handle_fifty(callback_update, user, question_id)
        if not callback_answered:
            _release_inline_button(callback_update)
        return
    if service.PUBLIC_HELP_HINT_KEY == hint_key:
        _handle_public_help(callback_update, user, question_id)
        _release_inline_button(callback_update)


def _handle_message(user, update, fail, current_question_id=0):
    if fail:
        _handle_lose(update, user)
        _release_inline_button(update)
        return

    max_user_answered_question_id = service.get_max_passed_question_id(user)
    if max_user_answered_question_id < current_question_id:
        _handle_retry(update)
        return

    max_question_id = service.get_max_question_id()
    if max_user_answered_question_id == max_question_id:
        _handle_win(update, user)
        _release_inline_button(update)
        return

    _send_next_question(update, user, max_user_answered_question_id)
    _release_inline_button(update)


def _handle_retry(update):
    retry_text = service.get_property(BOT_RETRY_TEXT, "Попробуйте еще раз")
    _show_notification_if_possible(update, retry_text)


def _send_next_question(update, user, current_question_id):
    question = service.get_question(current_question_id + 1)
    keyboard = _build_keyboard(question.question_id, {v.variant_id: v.text_value for v in question.variants}, service.get_available_hints(user))
    _reply(update, question.text_value, reply_markup=keyboard)


def _handle_win(update, user):
    win_text = service.get_property(BOT_WIN_TEXT, "Вы успешно ответили на все вопросы").format(player_place=service.get_user_place(user))
    _reply(update, win_text)


def _handle_lose(update, user):
    lose_text = service.get_property(BOT_LOSE_TEXT, "Игра закончена. Поздравляем! "
                                                    "Из {questions_count} вопросов вы смогли правильно ответить на {question_id}").format(
        questions_count=service.get_question_count(),
        question_id=service.get_max_passed_question_id(user)
    )
    _reply(update, lose_text)


def _handle_public_help(update, user, question_id):
    question = service.get_question(question_id)
    grouped, total_answer_count = service.get_answer_stats(question_id)
    answers_mapping = dict(grouped)
    keyboard = _build_keyboard(
        question.question_id,
        {v.variant_id: '{}({}%)'.format(v.text_value, _calculate_distribution(answers_mapping.get(v.variant_id, 0), total_answer_count)) for v in
         question.variants},
        service.get_available_hints(user),
        columns=1
    )
    update.effective_message.edit_reply_markup(reply_markup=keyboard)


def _calculate_distribution(target_answers_count, total_answers_count):
    return "{0:.2f}".format(target_answers_count / float(total_answers_count) * 100 if total_answers_count else 0)


def _handle_fifty(update, user, question_id):
    """
    :return: if callback_query answered
    """
    message = update.effective_message
    question = service.get_question(question_id)
    variants_to_leave = len(question.variants) - int(len(question.variants) / 2)
    if variants_to_leave <= 1:
        text = service.get_property(BOT_FIFTY_FOR_TWO_TEXT, 'Orly ^O,o^')
        return _show_notification_if_possible(text, update)

    rest = [variant for variant in question.variants if variant.correct]
    rest += random.sample([variant for variant in question.variants if not variant.correct], variants_to_leave - len(rest))
    keyboard = _build_keyboard(question.question_id, {v.variant_id: v.text_value for v in rest}, service.get_available_hints(user))
    message.edit_reply_markup(reply_markup=keyboard)
    return False


def _show_notification_if_possible(update, text):
    if update.callback_query:
        update.callback_query.answer(text='\n'.join(text.split('<br>')), parse_mode=ParseMode.HTML)
        return True
    return False


def _release_inline_button(update):
    # to release inline button
    if update.callback_query:
        update.callback_query.answer()


def place_handler(_, update):
    user = update.effective_user
    service.add_player(user, update.effective_message.chat_id, datetime.datetime.now())
    place = service.get_user_place(user)
    if place:
        place_text = service.get_property(BOT_PLACE_TEXT, 'Сейчас Вы на {player_place}м месте').format(player_place=place)
        _reply(update, place_text)
    else:
        start_handler(_, update)


def help_handler(_, update):
    help_text = service.get_property(BOT_HELP_TEXT, "Победить в нашей игре - легко!<br>Достаточно ответить на вопросы как можно быстрее, "
                                                    "использовав при этом минимум подсказок<br>"
                                                    "Если нужно повторить вопрос - просто поздоровайтесь с ботом")
    _reply(update, help_text)


def _reply(update, text, reply_markup=None):
    update.effective_message.reply_text('\n'.join(text.split('<br>')), parse_mode=ParseMode.HTML, reply_markup=reply_markup)


def error(_, update, err):
    logger.warning("Update '%s' caused error '%s'", update, err)


def _build_keyboard(question_id, key_text_variants, hints, columns=2):
    options = [InlineKeyboardButton('{}: {}'.format(variant_key, key_text_variants[variant_key]),
                                    callback_data=json.dumps(('answer', question_id, variant_key)))
               for variant_key in sorted(key_text_variants)]
    hints = [InlineKeyboardButton(hint['hint_title'], callback_data=json.dumps(('hint', hint['hint_key'], question_id)))
             for hint in hints]
    return InlineKeyboardMarkup(_build_menu(options, columns, footer_buttons=hints))


def _build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


if __name__ == "__main__":
    service.init()
    request_kwargs = {
        'proxy_url': os.environ['TG_PROXY_URL'], 'urllib3_proxy_kwargs': {}
        # Optional, if you need authentication:
        # 'urllib3_proxy_kwargs': {
        #     'username': 'PROXY_USER',
        #     'password': 'PROXY_PASS',
        # }
    } if os.environ['TG_PROXY_URL'] else {}
    updater = service.create_updater(os.environ['BOT_TOKEN'], os.environ['BOT_WORKERS'], request_kwargs)
    updater.dispatcher.add_handler(CommandHandler('help', help_handler))
    updater.dispatcher.add_handler(CommandHandler('start', start_handler))
    updater.dispatcher.add_handler(CommandHandler('place', place_handler))
    updater.dispatcher.add_handler(CallbackQueryHandler(answer_button_handler, pattern='\["answer"'))
    updater.dispatcher.add_handler(CallbackQueryHandler(hint_button_handler, pattern='\["hint"'))
    updater.dispatcher.add_handler(MessageHandler(Filters.all, start_handler))
    updater.dispatcher.add_error_handler(error)

    updater.start_polling()
    updater.idle()
