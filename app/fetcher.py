
import os
import re
import requests
import logging

from datetime import datetime, timedelta


logger = logging.getLogger()

GITHUB_ENDPOINT = 'https://api.github.com/graphql'

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

    closed_issues_set: issues(states: CLOSED, last: 30, filterBy: {{since: "{days_ago}"}}) {{
      nodes {{
        closedAt
        createdAt
      }}
    }}
    closed_prs_set: pullRequests(states: [CLOSED, MERGED], last: 30 ) {{
      nodes {{
        closedAt
        createdAt
      }}
    }}
}}
'''

QUERY_STRING = '''
query {{
    {repo_string}
}}
'''


class GitFetcher:
    def _fetch(self, url, method='GET', data={}):
        # set auth tokens
        token = os.getenv('GITHUB_TOKEN')
        error = 'GITHUB_TOKEN is not defined in the environment'
        assert token is not None, error

        if token is None:
            logger.error(error)
            raise Exception(error)

        req_headers = {
            'Authorization': f'Bearer {token}'
        }

        if method == 'GET':
            res = requests.get(url, headers=req_headers)
        else:
            res = requests.post(url, headers=req_headers, json=data)

        return res

    def _get_repos(self):
        repos = os.getenv('REPOS')
        error = 'REPOS is not defined in the environment'
        assert repos is not None, error
        
        if repos is None:
            logger.error(error)
            raise Exception(error)

        repos = repos.split(',')
        return repos

    def _clean(self, text):
        return re.sub(r'[-\._]', '', text)

    def days_ago(self, days=30):
        days_ago = datetime.utcnow() - timedelta(days=days)
        return days_ago.strftime('%Y-%m-%dT00:00:00')

    def fetch_stats(self):
        repos = self._get_repos()
        repo_queries = []

        for repo in repos:
            # split owner and repo name
            owner, repo = repo.split('/')
            clean_owner, clean_repo = self._clean(owner), self._clean(repo)
            repo_queries.append(
                REPO_STRING.format(
                    clean_owner=clean_owner,
                    owner=owner,
                    clean_repo=clean_repo,
                    repo=repo,
                    days_ago=self.days_ago(),
                )
            )

        data = QUERY_STRING.format(repo_string='\n'.join(repo_queries))
        res = self._fetch(GITHUB_ENDPOINT, method='POST', data={'query': data})

        if res.status_code != 200:
            # TODO check reason for fail rate limit/permission/general fail
            raise Exception("failed to fetch")

        return res.json(), res.headers
