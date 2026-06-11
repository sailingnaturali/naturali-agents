"""Entry point: uv run python -m poseidon"""
import asyncio
import logging

from poseidon import daemon

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    asyncio.run(daemon.run())
