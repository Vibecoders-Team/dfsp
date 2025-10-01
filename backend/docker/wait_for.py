import os, time, argparse, sys
import psycopg
import redis

def wait_db(dsn: str, deadline: float) -> None:
    while time.time() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            print("[wait] DB OK")
            return
        except Exception as e:
            print(f"[wait] DB not ready: {e}")
            time.sleep(1)
    print("[wait] DB timeout", file=sys.stderr)
    sys.exit(1)

def wait_redis(url: str, deadline: float) -> None:
    while time.time() < deadline:
        try:
            r = redis.Redis.from_url(url, socket_connect_timeout=5)
            if r.ping():
                print("[wait] Redis OK")
                return
        except Exception as e:
            print(f"[wait] Redis not ready: {e}")
            time.sleep(1)
    print("[wait] Redis timeout", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=int(os.getenv("WAIT_FOR_TIMEOUT", "60")))
    args = ap.parse_args()
    deadline = time.time() + args.timeout

    dsn = os.getenv("POSTGRES_DSN")
    if dsn.startswith("postgresql+psycopg://"):
        dsn = "postgresql://" + dsn.split("://", 1)[1]
    redis_url = os.getenv("REDIS_URL")

    if dsn:
        wait_db(dsn, deadline)
    else:
        print("[wait] POSTGRES_DSN not set -> skip DB wait")

    if redis_url:
        wait_redis(redis_url, deadline)
    else:
        print("[wait] REDIS_URL not set -> skip Redis wait")
