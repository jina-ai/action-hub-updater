FROM jinaai/jina:master

COPY entrypoint.sh /entrypoint.sh
COPY hub_updater.py /hub_updater.py

ENTRYPOINT ["/entrypoint.sh"]
