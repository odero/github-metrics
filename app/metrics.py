
import json
import logging

from datetime import datetime

from prometheus_client.core import GaugeMetricFamily

from .fetcher import GitFetcher

logger = logging.getLogger()


# TODO
# 1. open issues
# 2. closed issues
# 3. open PRS
# 4. merged PRs
# 5. closed PRs
# 6. stars

# all above (+ since yesterday)

class Limits:
    limit = -1
    remaining = -1
    reset = -1
    used = -1


class GitHubCollector:

    def build_name(self, name, namespace='github', subsystem='repo', unit='total'):
        return f'{namespace}_{subsystem}_{name}_{unit}'

    def set_limit_metrics(self, headers):
        logger.info('fetching limits..')
        limits = Limits()
        limits.limit = headers['X-RateLimit-Limit']
        limits.remaining = headers['X-RateLimit-Remaining']
        limits.used = headers['X-RateLimit-Used']
        limits.reset = headers['X-RateLimit-Reset']

        _build_name = lambda name, unit='total': self.build_name(name, subsystem='rate', unit=unit)

        self.limit_metrics = [
            GaugeMetricFamily(
                _build_name('limit'), 'Total number of API calls allowed in a 60 minute window', limits.limit
            ),
            GaugeMetricFamily(
                _build_name('remaining'), 'Total number of API calls remaining during the current window', limits.remaining
            ),
            GaugeMetricFamily(
                _build_name('used'), 'Total number of API calls made during the current window', limits.used
            ),
            GaugeMetricFamily(
                _build_name('reset', unit='seconds'), 'The time in UTC epoch seconds, when the current rate limit will reset', limits.reset
            ),
        ]

    def initialize(self):
        labels=['repo', 'fork', 'archived']
        self.repo_metrics = {
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
            'average_pr_open_time': GaugeMetricFamily(
                self.build_name('average_pr_open_time'), 'Average time PRs stay open before being closed', labels=labels
            ),
            'average_issue_open_time': GaugeMetricFamily(
                self.build_name('average_issue_open_time'), 'Average time issues stay open before being closed', labels=labels
            ),
        }

    def collect(self):
        self.initialize()
        client = GitFetcher()
        self.data, headers = client.fetch_stats()
        self.set_limit_metrics(headers)
        for limit_metric in self.limit_metrics:
            yield limit_metric

        self.set_repo_metrics()
        for _, metric in self.repo_metrics.items():
            yield metric

    def set_repo_metrics(self):
        for _, props in self.data['data'].items():
            label_values = [f'{props["name"]}', f'{props["isFork"]}', f'{props["isArchived"]}']
            self.repo_metrics['open_issues'].add_metric(label_values, props['open_issues']['totalCount'])
            self.repo_metrics['closed_issues'].add_metric(label_values, props['closed_issues']['totalCount'])
            self.repo_metrics['open_prs'].add_metric(label_values, props['open_prs']['totalCount'])
            self.repo_metrics['closed_prs'].add_metric(label_values, props['closed_prs']['totalCount'])
            self.repo_metrics['merged_prs'].add_metric(label_values, props['merged_prs']['totalCount'])
            self.repo_metrics['stars'].add_metric(label_values, props['stars'])
            self.repo_metrics['forks'].add_metric(label_values, props['forks'])

            self.repo_metrics['average_pr_open_time'].add_metric(label_values, self.get_average_pr_issue_open_time(props['closed_prs_set']['nodes']))
            self.repo_metrics['average_issue_open_time'].add_metric(label_values, self.get_average_pr_issue_open_time(props['closed_issues_set']['nodes']))
            # self.repo_metrics['active_pr_open_time']

    def get_average_pr_issue_open_time(self, nodes):
        diffs = []
        for row in nodes:
            closed_at = datetime.strptime(row['closedAt'], '%Y-%m-%dT%H:%M:%SZ')
            created_at = datetime.strptime(row['createdAt'], '%Y-%m-%dT%H:%M:%SZ')
            delta = closed_at - created_at
            diffs.append(delta.days)
        return sum(diffs)/len(diffs)
