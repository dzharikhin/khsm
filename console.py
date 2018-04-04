# coding=utf-8
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from telegram import Bot

import loggers
import service
from khsm_bot import BOT_STAGE

logger = loggers.logging.getLogger(__name__)


class Handler(BaseHTTPRequestHandler):

    def _write(self, text, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(text.encode('utf-8'))

    def do_GET(self):
        req_path = self.path[1:]
        dot_path = os.path.abspath(os.path.dirname(__file__))
        if not req_path:
            self._handle_index(dot_path)
        else:
            path_params = req_path.split('/')
            path = os.path.join(dot_path, 'templates/{}.html'.format(path_params[0]))
            if os.path.exists(path):
                with open(path, 'r') as f:
                    template = f.read()
                    self._write(template.format(','.join(path_params[1:])))
            else:
                self._write('ERROR', status=404)

    def do_POST(self):
        req_path = self.path[1:]
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = parse_qs(post_data)
        if req_path.startswith('message'):
            self._handle_message(params)
        elif req_path.startswith('release'):
            self._handle_release(params)
        elif req_path.startswith('stage'):
            self._handle_stage(params)
        else:
            self._write('ERROR', status=404)

    def _handle_index(self, dot_path):
        path = os.path.join(dot_path, 'templates/index.html')
        current_stage = service.get_property(BOT_STAGE, '1')
        top, question_amount = service.get_top(current_stage)
        header = '<tr><th>Place</th><th>Name</th><th>Points</th><th>Sum tries</th><th>Hint count</th><th>Latest answer</th><th>Chat</th></tr>\n'
        row_template = '<tr>' \
                       '<td>{place}</td>' \
                       '<td>{name}</td>' \
                       '<td>{points}</td>' \
                       '<td>{sum_tries}</td>' \
                       '<td>{hint_count}</td>' \
                       '<td>{latest_answer}</td>' \
                       '<td><a href="message/{chat_id}">Send message</a></td>' \
                       '</tr>'
        table = '\n'.join([row_template.format(place=i + 1, name=player[0], points=player[1], sum_tries=player[2], hint_count=player[3],
                                               latest_answer=player[4], chat_id=player[5]) for i, player in enumerate(top)])
        with open(path, 'r') as index_template:
            template = index_template.read()
            self._write(template.format(table=header + table))

    def _handle_message(self, params):
        if 'chat_ids' not in params:
            chat_ids = [player.chat_id for player in service.get_players()]
        else:
            chat_ids = '\n'.join(params.get('chat_ids', [])).split(',')
        msg = '\n'.join(params.get('msg', []))
        for chat_id in chat_ids:
            try:
                bot.send_message(chat_id=chat_id, text=msg)
            except Exception:
                logger.error('Error sending message', exc_info=True)
        self._write('OK')

    def _handle_release(self, params):
        current_stage = service.get_property(BOT_STAGE, '1')
        msg = '\n'.join(params.get('msg', []))
        service.release_losers(current_stage, lambda player: bot.send_message(chat_id=player.chat_id, text=msg))
        self._write('OK')

    def _handle_stage(self, params):
        stage = '\n'.join(params.get('stage', []))
        service.set_property(BOT_STAGE, stage)
        self._write('OK')


if __name__ == "__main__":
    service.init()
    global bot
    bot = Bot(os.environ['BOT_TOKEN'])
    server_address = ('', int(os.environ['CONSOLE_PORT']))
    httpd = HTTPServer(server_address, Handler)
    httpd.serve_forever()
