from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app
from prometheus_client.core import REGISTRY

import os
import json

from .metrics import GitHubCollector
from .fetcher import GitFetcher

fetcher = GitFetcher()
REGISTRY.register(GitHubCollector(fetcher))

app = Flask(__name__)

app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
    '/metrics': make_wsgi_app()
})


@app.route('/')
def index():
    app_name = os.getenv('APP_NAME')
    host = os.getenv('HOSTNAME', 'unknown')
    return f'Hello from {app_name}@{host}'

