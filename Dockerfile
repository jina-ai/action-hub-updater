FROM jinaai/jina:1.2.3

COPY entrypoint.sh /entrypoint.sh
COPY hub_updater.py /hub_updater.py

ENTRYPOINT ["/entrypoint.sh"]
