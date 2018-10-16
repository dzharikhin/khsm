import json
import os
from flask import Flask, render_template, request
from flask import send_from_directory
from flask_basicauth import BasicAuth
from flask import Response
from flask import redirect, url_for

import loggers
import service

logger = loggers.logging.getLogger(__name__)

app = Flask(__name__)
app.config['BASIC_AUTH_USERNAME'] = os.environ['CONSOLE_USERNAME']
app.config['BASIC_AUTH_PASSWORD'] = os.environ['CONSOLE_PASSWORD']
basic_auth = BasicAuth(app)


@app.route('/admin', methods=['GET'])
@basic_auth.required
def get_admin_page():
    top = service.get_top(False)
    return render_template('admin/index.html', top=top)


@app.route('/admin/message', methods=['GET'])
@basic_auth.required
def get_message_page():
    failed_chat_ids = request.args.get('failed_chat_ids', None)
    top = service.get_top(False)
    return render_template('admin/message.html', top=top, failed_chat_ids=failed_chat_ids)


@app.route('/admin/message', methods=['POST'])
@basic_auth.required
def post_message_page():
    # if request.form['username'] != os.environ['CONSOLE_USERNAME'] or request.form['password'] != os.environ['CONSOLE_PASSWORD']:
    #     error = 'Invalid Credentials. Please try again.'
    chat_ids = request.form.getlist('chat_id')
    message = request.form['message']
    failed_chat_ids = []
    for chat_id in chat_ids:
        try:
            bot.send_message(chat_id, message)
        except Exception as ex:
            failed_chat_ids.append(chat_id)
            logger.warning('Error sending to chat_id={}, ex={}'.format(chat_id, type(ex).__name__))
    return redirect(url_for('get_message_page', failed_chat_ids=",".join(failed_chat_ids)))


@app.route('/admin/properties', methods=['GET'])
@basic_auth.required
def get_properties_page():
    properties = service.get_properties()
    return render_template('admin/properties.html', properties=properties)


@app.route('/admin/properties', methods=['POST'])
@basic_auth.required
def post_properties_page():
    # if request.form['username'] != os.environ['CONSOLE_USERNAME'] or request.form['password'] != os.environ['CONSOLE_PASSWORD']:
    #     error = 'Invalid Credentials. Please try again.'
    properties = {k: v for k, v in zip(request.form.getlist('property_key'), request.form.getlist('property_value'))}
    service.save_properties(properties)
    return redirect(url_for('get_properties_page'))


@app.route('/admin/clear', methods=['GET'])
@basic_auth.required
def get_clear_data_page():
    top = service.get_top(False)
    return render_template('admin/clear-data.html', top=top)


@app.route('/admin/clear', methods=['POST'])
@basic_auth.required
def post_clear_data_page():
    player_ids = request.form.getlist('player_id')
    service.clear_data(player_ids)
    return redirect(url_for('get_clear_data_page'))


@app.route('/admin/rename', methods=['GET'])
@basic_auth.required
def get_rename_page():
    player = service.get_player(request.args['player_id'])
    return render_template('admin/rename.html', player=player)


@app.route('/admin/rename', methods=['POST'])
@basic_auth.required
def post_rename_page():
    player_id = request.form['player_id']
    name = request.form['player_name']
    service.rename_player(player_id, name)
    return redirect(url_for('get_admin_page'))


@app.route('/admin/questions', methods=['GET'])
@basic_auth.required
def get_questions_page():
    questions = service.get_questions()
    return render_template('admin/questions.html', questions=questions)


@app.route('/admin/questions', methods=['POST'])
@basic_auth.required
def post_questions_page():
    question_mark = 'question_'
    question_mark_len = len(question_mark)

    answer_mark = 'variant_'
    answer_mark_len = len(answer_mark)

    update_dict = {}
    for param_key, param_value in request.form.items():
        if param_key.startswith(question_mark):
            question_id = param_key[question_mark_len:]
            entry = update_dict.get(question_id, {'question_id': question_id, 'variants': []})
            entry['text_value'] = param_value
            update_dict[question_id] = entry
        else:
            variant_id_q_id_list = param_key[answer_mark_len:].split('_q_')
            question_entry = update_dict.get(variant_id_q_id_list[1], {'question_id': variant_id_q_id_list[1], 'variants':[]})
            question_entry['variants'].append({'variant_id': variant_id_q_id_list[0], 'text_value': param_value})
            update_dict[variant_id_q_id_list[1]] = question_entry
    service.update_questions(update_dict.values())
    return redirect(url_for('get_questions_page'))


@app.route('/rating/<path:path>', methods=['GET'])
def get_rating_page(path):
    return send_from_directory('templates/rating', path)


@app.route('/rating/data.js', methods=['GET'])
def get_rating_json():
    top = service.get_top()
    rating_data = json.dumps([{
        'place': player[0],
        'name': player[1].player_name,
        'points': player[2] if player[2] else 0,
        'sum_tries': player[3] if player[3] else 0,
        'hint_count': player[4] if player[4] else 0,
        'latest_answer': player[5].strftime('%Y-%m-%d %H:%M:%S') if player[5] else '',
        'chat_id': player[1].chat_id
    } for player in top])
    return Response('window.QUIZ_RESULTS = {}'.format(rating_data), mimetype='application/js')


if __name__ == "__main__":
    request_kwargs = {
        'proxy_url': os.environ['TG_PROXY_URL'], 'urllib3_proxy_kwargs': {}
        # Optional, if you need authentication:
        # 'urllib3_proxy_kwargs': {
        #     'username': 'PROXY_USER',
        #     'password': 'PROXY_PASS',
        # }
    } if os.environ['TG_PROXY_URL'] else {}
    service.init()
    updater = service.create_updater(os.environ['BOT_TOKEN'], 2, request_kwargs)
    global bot
    bot = updater.bot
    app.run(host='0.0.0.0', port=int(os.environ['CONSOLE_PORT']))
