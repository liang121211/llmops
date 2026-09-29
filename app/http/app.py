from dotenv import load_dotenv

load_dotenv()

import inject

from config import Config
from internal.handler.app_handler import AppHandler
from internal.router.router import Router
from internal.server.http import Http


def _configure(binder):
    binder.bind_to_constructor(AppHandler, AppHandler)
    binder.bind_to_constructor(Router, Router)


inject.clear_and_configure(_configure)

config = Config()

app = Http(inject.instance(Router), config)

if __name__ == "__main__":
    app.run()
