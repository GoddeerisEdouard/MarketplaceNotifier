from tortoise import run_async

from db import init

if __name__ == '__main__':
    run_async(init())
