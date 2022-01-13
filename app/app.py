from prometheus_client import start_http_server, Summary, Gauge
import random
import time

REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')
GAUGE = Gauge('my_inprogress_requests', 'Number of requests in progress')

GAUGE.set_to_current_time()

@GAUGE.track_inprogress()
@REQUEST_TIME.time()
def process_request(t):
    time.sleep(t)


if __name__ == '__main__':
    start_http_server(9000)
    print("Server started. Waiting for requests...")
    while True:
        process_request(random.random())
