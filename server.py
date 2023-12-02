import asyncio
import time
import json
from wsgiref.handlers import format_date_time
from pathlib import Path
from urllib.parse import unquote
from typing import Callable, Coroutine

import config


class VideoPlayerLauncher:
    def __init__(self):
        self.player = config.PLAYER
        if self.player == 'default':
            if config.OS == 'Linux':
                self.player = 'xdg-open'
            elif config.OS == 'Windows':
                self.player = 'start'

    async def play(self, path):
        command = f'{self.player} "{path}"'
        print(f'Running: <{command}>')

        # Create player process
        process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()

        print(f'Done: <{command} exited with {process.returncode}>')
        if stdout:
            print(f'[stdout]\n{stdout.decode()}')
        if stderr:
            print(f'[stderr]\n{stderr.decode()}')


class VideoPlayerServer:
    def __init__(self, request_data_handler: Callable[[str], Coroutine]):
        self.host = config.HOST
        self.port = config.PORT
        self.data_handler = request_data_handler
        self.server = None

    # Utils

    def parse_http_location(self, http_string):
        '''
        Parse path to video file from raw HTTP headers
        Request must be GET
        '''
        for line in http_string.split('\n'):
            if line.startswith('GET'):
                path = line.replace('GET ', '').replace(' HTTP/1.1', '')
                path = unquote(path) # Decode url encoded string
                return path.strip()

    def create_http_response(self, status, json_data):
        '''
        Generates raw HTTP response based on status code and json data
        '''
        headers = []
        headers.append(f'HTTP/2 {status}')
        headers.append(f'Content-Type: application/json')
        headers.append(f'Date: {format_date_time(time.time())}')
        headers.append('Connection: close')

        response = '\n'.join(headers) + '\n\n' + json.dumps(json_data)
        return response.encode()

    # Actual server

    async def process_request(self, reader, writer):
        '''
        Proceeds raw request and calls data_handler
        '''
        data = (await reader.read(2048)).decode('utf8')
        status = 200
        response_data = {'status': 1}

        file_path = Path(self.parse_http_location(data)).resolve()
        if not file_path.is_file():
            status = 404
            response_data['status'] = 0

        response = self.create_http_response(status, response_data)
        writer.write(response)
        writer.close()

        await writer.wait_closed()

        if file_path.is_file():
            loop = asyncio.get_event_loop()
            loop.create_task(self.data_handler(str(file_path)))

    async def run(self):
        '''
        Serve application
        '''
        print('Starting server...')
        loop = asyncio.get_event_loop()
        self.server = await asyncio.start_server(self.process_request, self.host, self.port)
        print(f'Server running on {self.host}:{self.port}')

        async with self.server:
            await self.server.serve_forever()


async def main():
    video_player = VideoPlayerLauncher()
    server = VideoPlayerServer(video_player.play)
    await server.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (asyncio.CancelledError, KeyboardInterrupt):
        print('\nExiting')
