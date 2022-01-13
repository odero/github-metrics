from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app, Summary, Gauge
from prometheus_client.core import GaugeMetricFamily, REGISTRY

import os
import re
import requests
import json

GITHUB_ENDPOINT = 'https://api.github.com/graphql' # 'https://api.github.com'

REPO_STRING = '''
{clean_owner}_{clean_repo}: repository(owner: "{owner}", name: "{repo}") {{
    open_issues: issues(states: OPEN) {{
        totalCount
    }}
    closed_issues: issues(states: CLOSED) {{
        totalCount
    }}
    open_prs: pullRequests(states: OPEN) {{
        totalCount
    }}
    closed_prs: pullRequests(states: CLOSED) {{
        totalCount
    }}
    merged_prs: pullRequests(states: MERGED) {{
        totalCount
    }}
    releases {{
        totalCount
    }}
    name
    isFork
    isArchived
    forks: forkCount
    stars: stargazerCount
}}
'''

QUERY_STRING = '''
query {{
    {repo_string}
}}
'''

app = Flask(__name__)

app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
    '/metrics': make_wsgi_app()
})

# REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')

# @REQUEST_TIME.time()
@app.route('/')
def index():
    app_name = os.getenv('APP_NAME', 'metrics')
    return f'Hello from {app_name}'


@app.route('/hello')
def hello():
    return 'hello from hello'

class Limits:
    limit = -1
    remaining = -1
    reset = -1

def get_limits(headers):
    limits = Limits()
    # limits.limit = headers['X-RateLimit-Limit']
    # limits.remaining = headers['x-ratelimit-remaining']
    # limits.used = headers['x-ratelimit-used']
    # limits.reset = headers['x-ratelimit-reset']
    app.logger.info({(k, v) for k, v in headers.items() if k.startswith('X-RateLimit-')})
    for key, val in headers.items():
        if not key.startswith('X-RateLimit-') or key == 'X-RateLimit-Resource':
            continue
        name = key.replace('X-','').replace('-', '_').lower()
        desc = key.replace('X-','').split('-')[-1].lower()
        g = Gauge(f'{name}_total', f'Rate limit {desc}')
        g.set(val)
    return limits


def fetch(url, method='GET', data={}):
    # set auth tokens
    token = os.getenv('GITHUB_TOKEN')
    req_headers = {
        'Authorization': f'Bearer {token}'
    }

    if method == 'GET':
        res = requests.get(url, headers=req_headers)
    else:
        res = requests.post(url, headers=req_headers, json=data)

    return res
    # if res.status_code != 200:
    #     raise Exception(f'we failed to fetch {url}')
    # return res.content

def get_repos():
    repos = os.getenv('REPOS')
    assert repos is not None, "REPOS is not defined"
    
    if repos is None:
        msg = "REPOS is not defined"
        app.logger.error(msg)
        raise Exception(msg)

    repos = repos.split(',')
    return repos
    

def clean(text):
    return re.sub(r'[-\._]', '', text)


@app.route('/git')
def fetch_stats():
    repos = get_repos()
    repo_queries = []
    for repo in repos:
        # split owner and repo name
        owner, repo = repo.split('/')
        clean_owner, clean_repo = clean(owner), clean(repo)
        repo_queries.append(
            REPO_STRING.format(
                clean_owner=clean_owner, owner=owner, clean_repo=clean_repo, repo=repo
            )
        )

    data = QUERY_STRING.format(repo_string='\n'.join(repo_queries))
    res = fetch(GITHUB_ENDPOINT, method='POST', data={'query': data})

    if res.status_code != 200:
        # TODO check reason for fail rate limit/permission/general fail
        raise Exception("failed to fetch")

    # get_limits(res.headers)
    # emit_stats(res.json())

    return res.json()




class PromCollector:

    def build_name(self, name, namespace='github', subsystem='repo', unit='total'):
        return f'{namespace}_{subsystem}_{name}_{unit}'
    
    def initialize(self):
        labels=['repo', 'fork', 'archived']
        self.metrics = {
            'open_issues' : GaugeMetricFamily(
                self.build_name('open_issues'), 'Total number of open issues', labels=labels
            ),
            'closed_issues' : GaugeMetricFamily(
                self.build_name('closed_issues'), 'Total number of closed issues', labels=labels
            ),
            'open_prs' : GaugeMetricFamily(
                self.build_name('open_prs'), 'Total number of open pull requests', labels=labels
            ),
            'closed_prs' : GaugeMetricFamily(
                self.build_name('closed_prs'), 'Total number of closed pull requests', labels=labels
            ),
            'merged_prs' : GaugeMetricFamily(
                self.build_name('merged_prs'), 'Total number of merged pull requests', labels=labels
            ),
            'stars' : GaugeMetricFamily(
                self.build_name('stars'), 'Total number of stars', labels=labels
            ),
            'forks' : GaugeMetricFamily(
                self.build_name('forks'), 'Total number of forks', labels=labels
            ),
        }

    def collect(self):
        self.initialize()
        data = fetch_stats()
        for _, props in data['data'].items():
            label_values = [f'{props["name"]}', f'{props["isFork"]}', f'{props["isArchived"]}']
            self.metrics['open_issues'].add_metric(label_values, props['open_issues']['totalCount'])
            self.metrics['closed_issues'].add_metric(label_values, props['closed_issues']['totalCount'])
            self.metrics['open_prs'].add_metric(label_values, props['open_prs']['totalCount'])
            self.metrics['closed_prs'].add_metric(label_values, props['closed_prs']['totalCount'])
            self.metrics['merged_prs'].add_metric(label_values, props['merged_prs']['totalCount'])
            self.metrics['stars'].add_metric(label_values, props['stars'])
            self.metrics['forks'].add_metric(label_values, props['forks'])
            
        for _, metric in self.metrics.items():
            yield metric


REGISTRY.register(PromCollector())



def emit_stats(data):
    for repo, val in list(data['data'].items())[:1]:
        app.logger.info(f'value: {val}')
        yield GaugeMetricFamily(
            'open_issues', 'Number of open issues',
            ['repo', 'fork'],
            'github', 'repo', 'total',
        ).add_metric([f'{val["name"]}', f'{val["isFork"]}'], val['openIssues']['totalCount'])
        # Gauge(
        #     'open_issues', 'Number of open issues',
        #     ['repo', 'fork'],
        #     'github', 'repo', 'total',
        # ).labels(repo=f'{val["name"]}', fork=f'{val["isFork"]}').set(val['openIssues']['totalCount'])
        # Gauge(
        #     'closed_issues', 'Number of closed issues',
        #     namespace='github', subsystem='repo', unit='total',
        #     labelnames=['repo', 'fork'],
        # ).labels(repo=f'{val["name"]}', fork=f'{val["isFork"]}').set(val['closedIssues']['totalCount'])
        # Gauge(
        #     'open_prs', 'Number of open PRs',
        #     namespace='github', subsystem='repo', unit='total',
        #     labelnames=['repo', 'fork'],
        # ).labels(repo=f'{repo}', fork=f'{fork}').set(310)
        # Gauge(
        #     'closed_prs', 'Number of closed PRs',
        #     namespace='github', subsystem='repo', unit='total',
        #     labelnames=['repo', 'fork'],
        # ).labels(repo=f'{repo}', fork=f'{fork}').set(310)
        # Gauge(
        #     'merged_prs', 'Number of merged PRs',
        #     namespace='github', subsystem='repo', unit='total',
        #     labelnames=['repo', 'fork'],
        # ).labels(repo=f'{repo}', fork=f'{fork}').set(310)
        # Gauge(
        #     'stars', 'Number of stars for the repo',
        #     namespace='github', subsystem='repo', unit='total',
        #     labelnames=['repo', 'fork'],
        # ).labels(repo=f'{repo}', fork=f'{fork}').set(310)
        # Gauge(
        #     'forks', 'Number of forks for the repo',
        #     namespace='github', subsystem='repo', unit='total',
        #     labelnames=['repo', 'fork'],
        # ).labels(repo=f'{repo}', fork=f'{fork}').set(310)
        


# TODO
# 1. open issues
# 2. closed issues
# 3. open PRS
# 4. merged PRs
# 5. closed PRs
# 6. stars

# all above (+ since yesterday)
