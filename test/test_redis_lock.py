import threading
import time

import pytest

from internal.lib.redis_lock import (
    LockAcquireError,
    document_status_lock_key,
    keyword_table_lock_key,
    redis_lock,
    segment_enabled_lock_key,
)


class TestLockKeys:
    """锁键命名规则测试。"""

    def test_document_status_lock_key(self):
        assert document_status_lock_key("abc") == "lock:document_status:abc"

    def test_keyword_table_lock_key(self):
        assert keyword_table_lock_key("abc") == "lock:keyword_table:abc"

    def test_segment_enabled_lock_key(self):
        assert segment_enabled_lock_key("abc") == "lock:segment_enabled:abc"


class TestRedisLock:
    """分布式锁行为测试，依赖本地 Redis。"""

    @pytest.fixture(autouse=True)
    def setup(self, app_context):
        from flask import current_app

        # 后台线程无法使用 current_app 代理，需捕获真实 app 对象
        self.app = current_app._get_current_object()
        self.redis = current_app.extensions["redis"]
        yield
        # 用例可能残留测试锁，按前缀清掉
        for key in self.redis.keys("lock_test/*"):
            self.redis.delete(key)

    def test_acquire_and_release(self):
        with redis_lock("lock_test/basic", blocking_timeout=1):
            assert self.redis.get("lock_test/basic") is not None
        # 退出代码块后锁被释放
        assert self.redis.get("lock_test/basic") is None

    def test_mutual_exclusion(self):
        with redis_lock("lock_test/basic", blocking_timeout=1):
            # 同一把锁未释放时，第二个获取者在超时后抛异常
            with pytest.raises(LockAcquireError):
                with redis_lock("lock_test/basic", blocking_timeout=0.2):
                    pass

    def test_different_keys_not_blocked(self):
        with redis_lock("lock_test/a", blocking_timeout=1):
            with redis_lock("lock_test/b", blocking_timeout=1):
                pass

    def test_blocking_waits_until_released(self):
        released = threading.Event()

        def _hold():
            with self.app.app_context():
                with redis_lock("lock_test/basic", blocking_timeout=5):
                    released.wait(0.3)

        holder = threading.Thread(target=_hold)
        holder.start()
        time.sleep(0.05)
        start = time.monotonic()
        with redis_lock("lock_test/basic", blocking_timeout=5):
            waited = time.monotonic() - start
        holder.join()
        # 第二个获取者应当等待到锁释放后才拿到（而不是立刻失败）
        assert 0.05 < waited < 5

    def test_ttl_auto_release(self):
        # 超时时间 1 秒，模拟持有者崩溃后锁自动释放
        with redis_lock("lock_test/ttl", timeout=1, blocking_timeout=0.1):
            pass
        time.sleep(1.3)
        assert self.redis.get("lock_test/ttl") is None

    def test_default_timeout_from_config(self):
        from flask import current_app

        config_ttl = int(current_app.config.get("REDIS_LOCK_TIMEOUT") or 600)
        assert config_ttl == 600
