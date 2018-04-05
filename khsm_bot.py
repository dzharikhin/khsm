# coding=utf-8

import datetime
import os
import random

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

import loggers
import service

logger = loggers.logging.getLogger(__name__)

BOT_GREETING_TEXT = 'bot_greeting_text'
BOT_WIN_TEXT = 'bot_win_text'
BOT_LOSE_TEXT = 'bot_lose_text'
BOT_CONTACT_REQUIRE_TEXT = 'bot_contact_request_text'
BOT_FINAL_TEXT = 'bot_final_text'

BOT_PLACE_TEXT = 'bot_place_text'
BOT_HINT_DOUBLE_TEXT = 'bot_hint_double_text'
BOT_REPEAT_TEXT = 'bot_repeat_text'
BOT_HELP_TEXT = 'bot_help_text'

BOT_STAGE = 'bot_stage'
BOT_SKIP_REPLY = 'bot_skip_reply'
BOT_TRY_LIMIT = 'bot_try_limit'

PLAYER_TYPE = 'TG'


def start_handler(bot, update):
    user = update.message.from_user
    player = service.add_player(str(user.id), PLAYER_TYPE, user.username, update.message.chat_id, 'INIT', datetime.datetime.now())
    current_stage = service.get_property(BOT_STAGE, '1')
    player, question = service.get_current_ctx(player.player_id, current_stage)
    handle_reply(update.message, player, question)


def handle_reply(message, player, question):
    try_limit = int(service.get_property(BOT_TRY_LIMIT, '2'))
    current_stage = service.get_property(BOT_STAGE, '1')
    if player.state in ['WIN', 'LOSE']:
        state = service.get_game_state(current_stage, player, try_limit)
        player = service.set_player_state(player, state)
    if player.state == 'CONTACT_REQUEST':
        if message.text.startswith('/start'):
            player = service.set_player_state(player, 'CONTACT')
        else:
            state = service.get_game_state(current_stage, player, try_limit)
            player = service.save_player_contacts(player, '\n'.join([part for part in [player.contacts, message.text] if part is not None]), state)
    if player.state == 'INIT':
        _reply_to_player(message, service.get_property(BOT_GREETING_TEXT, """Добро пожаловать в игру!
Победит тот, кто ответит на самое большое количество вопросов как можно быстрее, использовав при этом минимум попыток и подсказок. 
Ах, да.. подсказки! Их две:
/fiftyfifty - уберет половину неправильных вариантов из текущего вопроса
/jpoint_help - покажет текущее распределение ответов на текущий вопрос
Подробнее можно почитать в /help
Поехали!
"""))
        player = service.set_player_state(player, 'PLAY')
    if player.state == 'REPEAT':
        _reply_to_player(message, text=service.get_property(BOT_REPEAT_TEXT, 'Ошибка.. Попробуй еще раз!'), force_reply=True)
        player = service.set_player_state(player, 'PLAY')
    if player.state == 'PLAY':
        if question:
            _reply_to_player(message, text=question.text_value, reply_markup=_build_keyboard(question.variants), force_reply=True)
        else:
            player = service.set_player_state(player, 'WIN')
    if player.state == 'WIN':
        _reply_to_player(message, service.get_property(BOT_WIN_TEXT, 'Поздравляем! Все вопросы - позади! Следи за /top и временем награждения'))
        if not player.contacts:
            player = service.set_player_state(player, 'CONTACT')
    if player.state == 'LOSE':
        _reply_to_player(message, service.get_property(BOT_LOSE_TEXT, 'К сожалению, твоя игра окончена('))
        if not player.contacts:
            player = service.set_player_state(player, 'CONTACT')
    if player.state == 'CONTACT':
            _reply_to_player(message, service.get_property(BOT_CONTACT_REQUIRE_TEXT, 'Оставь нам контактную информацию - телефон, email '
                                                                                     'и как к Тебе обращаться?)'))
            player = service.set_player_state(player, 'CONTACT_REQUEST')


def button_handler(bot, callback_update):
    user = callback_update.effective_user
    current_stage = service.get_property(BOT_STAGE, '1')
    player, question = service.get_current_ctx(str(user.id), current_stage)
    if player.state in ['PLAY', 'REPEAT']:
        try_limit = int(service.get_property(BOT_TRY_LIMIT, '2'))
        player, question = service.process_answer(current_stage, player, callback_update.callback_query.data, datetime.datetime.now(), try_limit)
    handle_reply(callback_update.effective_message, player, question)


def public_help_handler(bot, update):
    user = update.message.from_user
    current_stage = service.get_property(BOT_STAGE, '1')
    player, question = service.get_current_ctx(str(user.id), current_stage)
    if not player:
        start_handler(bot, update)
        return
    if player.state in ['PLAY', 'REPEAT']:
        already_used_hint = service.add_hint(player.player_id, question.question_id, 'ZAL_HELP')
        if already_used_hint:
            _reply_to_player(update.message, service.get_property(BOT_HINT_DOUBLE_TEXT, 'Подсказка больше не доступна)'))
            return

        grouped, total = service.get_answer_stats(question.question_id)
        text = '\n'.join(['{} - {}%'.format(variant[0], variant[1] / float(total) * 100 if total else 0) for variant in grouped])
        _reply_to_player(update.message, text)
    else:
        handle_reply(update.message, player, question)


def fifty_handler(bot, update):
    user = update.message.from_user
    current_stage = service.get_property(BOT_STAGE, '1')
    player, question = service.get_current_ctx(str(user.id), current_stage)
    if not player:
        start_handler(bot, update)
        return
    if player.state in ['PLAY', 'REPEAT']:
        already_used_hint = service.add_hint(player.player_id, question.question_id, 'FIFTY')
        if already_used_hint:
            _reply_to_player(update.message, service.get_property(BOT_HINT_DOUBLE_TEXT, 'Подсказка больше не доступна)'))
            return
        variants_to_leave = len(question.variants) - int(len(question.variants) / 2)
        if variants_to_leave > 1:
            rest = [variant for variant in question.variants if variant.correct]
            rest += random.sample([variant for variant in question.variants if not variant.correct], variants_to_leave - len(rest))
            _reply_to_player(update.message, text=question.text_value, reply_markup=_build_keyboard(rest), force_reply=True)
    else:
        handle_reply(update.message, player, question)


def top_handler(bot, update):
    user = update.message.from_user
    current_stage = service.get_property(BOT_STAGE, '1')
    top, question_amount = service.get_top(current_stage, 10)
    if top:
        text = '\n'.join(['{bold}{index}. {username} - {points}pts{bold}'.format(index=i + 1, username=player[0], points=player[1],
                                                                              bold='*' if player[6] == str(user.id) else '')
                          for i, player in enumerate(top)])
        if not next((player for player in top if player[6] == str(user.id)), None):
            player_score, player_place = service.get_player_place(current_stage, str(user.id))
            if player_score:
                text = '\n'.join([text, '...', '*{}. {} - {}pts*'.format(player_place, user.username, player_score[1])])

        _reply_to_player(update.message, text, parse_mode=telegram.ParseMode.MARKDOWN)
    else:
        start_handler(bot, update)


def contact_handler(bot, update):
    user = update.message.from_user
    player = service.add_player(str(user.id), PLAYER_TYPE, user.username, update.message.chat_id, 'INIT', datetime.datetime.now())
    player = service.set_player_state(player, 'CONTACT')
    handle_reply(update.message, player, None)


def help_handler(bot, update):
    help_text = service.get_property(BOT_HELP_TEXT, """Список команд:
/start - начать игру. Игру также начнет любое произвольное сообщение
/jpoint_help - как распределились ответы на текущий вопрос. Доступна один раз
/fiftyfifty - убрать половину неверных вариантов. Доступна один раз
/top - покажет игровой рейтинг 
/contacts - оставьте нам контактную информацию для связи. Возможно, это учитывается в рейтинге;)
""")
    _reply_to_player(update.message, help_text)


def error(bot, update, err):
    logger.warning("Update '%s' caused error '%s'", update, err)


def _reply_to_player(message, text, *args, **kwargs):
    if not service.get_property(BOT_SKIP_REPLY, '') or kwargs.get('force_reply', False):
        message.reply_text(text, *args, **kwargs)


def _build_keyboard(variants):
    options = [InlineKeyboardButton(variant.text_value, callback_data=variant.variant_id)
               for variant in sorted(variants, key=lambda x: x.variant_id)]
    return InlineKeyboardMarkup(_build_menu(options, n_cols=1))


def _build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


def get_bot():
    return updater.bot


def main():
    global updater
    updater = Updater(os.environ['BOT_TOKEN'], workers=int(os.environ['WORKERS']))
    updater.dispatcher.add_handler(CommandHandler('help', help_handler))
    updater.dispatcher.add_handler(CommandHandler('start', start_handler))
    updater.dispatcher.add_handler(CommandHandler('jpoint_help', public_help_handler))
    updater.dispatcher.add_handler(CommandHandler('fiftyfifty', fifty_handler))
    updater.dispatcher.add_handler(CommandHandler('top', top_handler))
    updater.dispatcher.add_handler(CommandHandler('contacts', contact_handler))
    updater.dispatcher.add_handler(CallbackQueryHandler(button_handler))
    updater.dispatcher.add_handler(MessageHandler(Filters.all, start_handler))
    updater.dispatcher.add_error_handler(error)

    updater.start_polling()
    updater.idle()
