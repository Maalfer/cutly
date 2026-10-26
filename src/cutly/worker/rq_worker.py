"""Punto de entrada del worker: `python -m cutly.worker.rq_worker`."""

from redis import Redis
from rq import Queue, Worker

from cutly.config import get_settings
from cutly.db.session import init_db


def main() -> None:
    init_db()
    conn = Redis.from_url(get_settings().redis_url)
    Worker([Queue(connection=conn)], connection=conn).work()


if __name__ == "__main__":
    main()
